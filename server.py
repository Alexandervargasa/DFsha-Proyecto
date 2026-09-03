"""
DFSha - Hito 1: Servidor monolitico (C/S, un solo nodo)
Implementa RF1 (gestion del filesystem) y RF2 (transferencia de archivos).

Todos los archivos se guardan en un directorio raiz local (ROOT_DIR).
Las rutas que manda el cliente son siempre relativas a ese raiz;
se valida que nunca "escapen" del raiz (proteccion basica de path traversal).
"""

import os
import logging
from concurrent import futures

import grpc

import dfsha_pb2
import dfsha_pb2_grpc

ROOT_DIR = os.path.abspath(os.environ.get("DFSHA_ROOT", "./server_storage"))
CHUNK_SIZE = 1024 * 1024  # 1 MB por chunk

logging.basicConfig(level=logging.INFO, format="%(asctime)s [server] %(message)s")
log = logging.getLogger("dfsha.server")


def resolve(path: str) -> str:
    """Convierte una ruta virtual del cliente en una ruta absoluta segura
    dentro de ROOT_DIR. Lanza ValueError si intenta salirse del raiz."""
    clean = os.path.normpath("/" + path.lstrip("/"))
    full = os.path.abspath(os.path.join(ROOT_DIR, clean.lstrip("/")))
    if not (full == ROOT_DIR or full.startswith(ROOT_DIR + os.sep)):
        raise ValueError("Ruta invalida: intenta salir del filesystem del servicio")
    return full


class DFSServiceServicer(dfsha_pb2_grpc.DFSServiceServicer):

    def Ls(self, request, context):
        try:
            full = resolve(request.path)
            if not os.path.isdir(full):
                return dfsha_pb2.LsResponse(ok=False, message="No es un directorio o no existe")
            entries = []
            for name in sorted(os.listdir(full)):
                p = os.path.join(full, name)
                entries.append(dfsha_pb2.DirEntry(
                    name=name,
                    is_dir=os.path.isdir(p),
                    size_bytes=0 if os.path.isdir(p) else os.path.getsize(p),
                ))
            return dfsha_pb2.LsResponse(ok=True, message="OK", entries=entries)
        except Exception as e:
            log.exception("Ls error")
            return dfsha_pb2.LsResponse(ok=False, message=str(e))

    def Mkdir(self, request, context):
        try:
            full = resolve(request.path)
            os.makedirs(full, exist_ok=False)
            log.info("mkdir %s", request.path)
            return dfsha_pb2.StatusResponse(ok=True, message="Directorio creado")
        except FileExistsError:
            return dfsha_pb2.StatusResponse(ok=False, message="Ya existe")
        except Exception as e:
            log.exception("Mkdir error")
            return dfsha_pb2.StatusResponse(ok=False, message=str(e))

    def Rmdir(self, request, context):
        try:
            full = resolve(request.path)
            os.rmdir(full)  # falla si no esta vacio -> comportamiento esperado de rmdir
            log.info("rmdir %s", request.path)
            return dfsha_pb2.StatusResponse(ok=True, message="Directorio eliminado")
        except Exception as e:
            log.exception("Rmdir error")
            return dfsha_pb2.StatusResponse(ok=False, message=str(e))

    def Rm(self, request, context):
        try:
            full = resolve(request.path)
            if os.path.isdir(full):
                return dfsha_pb2.StatusResponse(ok=False, message="Es un directorio, use rmdir")
            os.remove(full)
            log.info("rm %s", request.path)
            return dfsha_pb2.StatusResponse(ok=True, message="Archivo eliminado")
        except Exception as e:
            log.exception("Rm error")
            return dfsha_pb2.StatusResponse(ok=False, message=str(e))

    def Send(self, request_iterator, context):
        """RF2: el cliente sube un archivo como stream de chunks."""
        dest_full = None
        f = None
        try:
            total = 0
            for chunk in request_iterator:
                if dest_full is None:
                    dest_full = resolve(chunk.path)
                    os.makedirs(os.path.dirname(dest_full), exist_ok=True)
                    f = open(dest_full, "wb")
                f.write(chunk.data)
                total += len(chunk.data)
            if f:
                f.close()
            log.info("send: %d bytes recibidos -> %s", total, dest_full)
            return dfsha_pb2.StatusResponse(ok=True, message=f"{total} bytes recibidos")
        except Exception as e:
            if f:
                f.close()
            log.exception("Send error")
            return dfsha_pb2.StatusResponse(ok=False, message=str(e))

    def Receive(self, request, context):
        """RF2: el servidor envia el archivo pedido como stream de chunks."""
        try:
            full = resolve(request.path)
            if not os.path.isfile(full):
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Archivo no encontrado")
                return
            with open(full, "rb") as f:
                while True:
                    data = f.read(CHUNK_SIZE)
                    if not data:
                        break
                    yield dfsha_pb2.FileChunk(path=request.path, data=data)
            log.info("receive: %s enviado", request.path)
        except Exception as e:
            log.exception("Receive error")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))


def serve(port: int = 50051):
    os.makedirs(ROOT_DIR, exist_ok=True)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    dfsha_pb2_grpc.add_DFSServiceServicer_to_server(DFSServiceServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info("DFSha server escuchando en puerto %d, raiz=%s", port, ROOT_DIR)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
