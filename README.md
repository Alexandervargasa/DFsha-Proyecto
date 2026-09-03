# DFSha — Distributed File System with High Availability

**SI3007 Sistemas Distribuidos — Proyecto 1**
**Opción asignada: 2 — P2P con SuperPeers**

> Este repositorio contiene el **Hito 1**: una versión monolítica
> Cliente/Servidor (un solo nodo servidor) que implementa completos los
> requerimientos funcionales RF1 (gestión del sistema de archivos) y RF2
> (transferencia de archivos). Es la base funcional sobre la que se
> construirán los siguientes hitos hasta llegar a la arquitectura P2P con
> SuperPeers definitiva.

---

## Tabla de contenidos

- [1. Definición del servicio](#1-definición-del-servicio)
- [2. Arquitectura del sistema (hito 1)](#2-arquitectura-del-sistema-hito-1)
- [3. Estructura del repositorio](#3-estructura-del-repositorio)
- [4. Cómo ejecutar](#4-cómo-ejecutar)
  - [4.1 Local (sin Docker)](#41-local-sin-docker)
  - [4.2 Con Docker Compose](#42-con-docker-compose)
  - [4.3 Contenedores separados (sin compose)](#43-contenedores-separados-sin-compose)
- [5. Comandos del cliente](#5-comandos-del-cliente)
- [6. Guía de prueba rápida](#6-guía-de-prueba-rápida)
- [7. Decisiones de diseño](#7-decisiones-de-diseño)
- [8. Fuera de alcance en este hito](#8-fuera-de-alcance-en-este-hito)

---

## 1. Definición del servicio

### 1.1 Objetivo del hito

Diseñar e implementar una primera versión funcional del sistema DFSha bajo
una arquitectura Cliente/Servidor monolítica (un único nodo servidor, sin
distribución ni replicación todavía), cubriendo de forma completa RF1
(gestión del sistema de archivos) y RF2 (transferencia de archivos). Esta
versión sirve como base de referencia correcta y probada antes de
introducir la complejidad de la arquitectura distribuida definitiva
(Opción 2: P2P con SuperPeers).

### 1.2 Alcance funcional

**RF1 — Gestión del sistema de archivos**
- `ls` — listar el contenido de un directorio.
- `cd` — cambiar de directorio de trabajo (manejado en el cliente; el
  servidor es *stateless*).
- `mkdir` / `rmdir` — crear y eliminar directorios.
- `rm` — eliminar archivos.

**RF2 — Transferencia de archivos**
- `send()` — subir un archivo local al servidor.
- `receive()` — descargar un archivo del servidor al cliente.

---

## 2. Arquitectura del sistema (hito 1)

### 2.1 Tipo de arquitectura

Cliente/Servidor clásico de un solo nodo servidor (sin composición ni
distribución servidor-servidor todavía). El cliente y el servidor se
comunican mediante llamadas a procedimiento remoto (RPC) usando **gRPC**,
que usa **Protocol Buffers** como formato de serialización y **HTTP/2**
como transporte.

```
┌────────────────────┐   gRPC (HTTP/2 +   ┌──────────────────────┐   I/O de   ┌────────────────────┐
│   Cliente DFSha     │   Protobuf)        │   Servidor DFSha      │   archivos │  Almacenamiento     │
│   (CLI)              │ ─────────────────▶ │   (gRPC, mono-nodo)    │ ─────────▶ │  local               │
│   RF1 / RF2           │                    │   lógica RF1 / RF2      │            │  (server_storage/)   │
└────────────────────┘                    └──────────────────────┘            └────────────────────┘
```

### 2.2 Componentes

| Componente | Responsabilidad |
|---|---|
| **Cliente DFSha (CLI)** | Shell interactivo (`ls`, `cd`, `pwd`, `mkdir`, `rmdir`, `rm`, `send`, `recv`). Mantiene el directorio de trabajo (`cwd`) localmente y resuelve rutas relativas antes de invocar al servidor. |
| **Servidor DFSha** | Único proceso que expone el servicio gRPC `DFSService`. Valida rutas, ejecuta las operaciones del filesystem y sirve/recibe archivos por streaming. |
| **Almacenamiento local** | Carpeta raíz en el disco del servidor (`server_storage/` o `/data` en Docker) donde se guardan físicamente directorios y archivos. |

### 2.3 Protocolo de comunicación

Definido en [`proto/dfsha.proto`](proto/dfsha.proto):

| RPC | Tipo / Descripción |
|---|---|
| `Ls(path)` | Unario. Devuelve el listado de entradas (nombre, tipo, tamaño) de un directorio. |
| `Mkdir(path)` / `Rmdir(path)` / `Rm(path)` | Unarios. Ejecutan la operación y devuelven `ok`/mensaje. |
| `Send(stream FileChunk)` | Client-streaming. El cliente envía el archivo en chunks de 1 MB; el servidor lo reconstruye en disco. |
| `Receive(path)` | Server-streaming. El servidor envía el archivo solicitado en chunks de 1 MB. |

---

## 3. Estructura del repositorio

```
.
├── proto/
│   └── dfsha.proto          # contrato del servicio (IDL)
├── dfsha_pb2.py              # stubs generados (mensajes)
├── dfsha_pb2_grpc.py         # stubs generados (servicio)
├── server.py                 # servidor monolítico (RF1 + RF2)
├── client.py                 # cliente CLI / shell interactivo
├── requirements.txt
├── Dockerfile.server
├── Dockerfile.client
├── docker-compose.yml
├── .dockerignore
└── README.md
```

---

## 4. Cómo ejecutar

### 4.1 Local (sin Docker)

```bash
pip install -r requirements.txt

# Terminal 1
python server.py
# escucha en el puerto 50051, guarda archivos en ./server_storage
# (variable de entorno opcional DFSHA_ROOT para cambiar la carpeta raíz)

# Terminal 2
python client.py --host localhost --port 50051
```

Si editas `proto/dfsha.proto`, regenera los stubs con:

```bash
python -m grpc_tools.protoc -I proto --python_out=. --grpc_python_out=. proto/dfsha.proto
```

### 4.2 Con Docker Compose

Requiere Docker Desktop corriendo (modo *Linux containers*).

```bash
docker compose up --build -d server   # construye y levanta el servidor en background
docker compose run --rm client        # abre el shell interactivo del cliente
```

- El servidor guarda los archivos en el volumen `dfsha_data` (persiste
  entre reinicios del contenedor).
- El cliente monta `./local-files` (carpeta local, junto al
  `docker-compose.yml`) como `/work` dentro del contenedor: los archivos
  que quieras subir con `send` deben estar ahí, y lo que descargues con
  `recv` va a aparecer ahí.
- El cliente se conecta a `server:50051` porque Docker Compose resuelve el
  nombre del servicio (`server`) como hostname dentro de la red interna
  `dfsha-net`.

Para apagar todo: `docker compose down`.

### 4.3 Contenedores separados (sin compose)

Útil para desplegar servidor y cliente en máquinas distintas (por ejemplo
dos VMs), como se espera para los hitos con múltiples nodos.

```bash
# En el nodo servidor
docker build -f Dockerfile.server -t dfsha-server .
docker run -d --name dfsha-server -p 50051:50051 -v dfsha_data:/data dfsha-server

# En el nodo cliente (ajustando --host a la IP/puerto público del servidor)
docker build -f Dockerfile.client -t dfsha-client .
docker run -it --rm -v $(pwd)/local-files:/work dfsha-client --host <IP_DEL_SERVIDOR> --port 50051
```

---

## 5. Comandos del cliente

```
ls [path]                             listar contenido de un directorio
cd <path>                             cambiar directorio de trabajo
pwd                                   mostrar directorio actual
mkdir <path>                          crear directorio
rmdir <path>                          eliminar directorio (debe estar vacío)
rm <path>                             eliminar archivo
send <archivo_local> [ruta_remota]    subir un archivo (RF2)
recv <ruta_remota> [archivo_local]    descargar un archivo (RF2)
exit                                  salir del shell
```

---

## 6. Guía de prueba rápida

1. Crea `local-files/prueba.txt` con algún texto (o usa el archivo que
   quieras subir).
2. `docker compose run --rm client`
3. Dentro del shell: `mkdir docs` → `ls` → `send prueba.txt docs/prueba.txt`
   → `ls docs` → `recv docs/prueba.txt copia.txt`
4. Sal con `exit` y verifica que `local-files/copia.txt` existe y su
   contenido coincide con el original.
5. (Opcional, limpieza) `rm docs/prueba.txt` y `rmdir docs`.

Si los pasos 3 y 4 funcionan sin errores y el contenido coincide, RF1 y
RF2 quedan verificados de punta a punta.

---

## 7. Decisiones de diseño

- **Servidor stateless por diseño**: cada RPC lleva la ruta absoluta ya
  resuelta; `cd` solo actualiza estado en el cliente. Esto facilita
  evolucionar después hacia múltiples nodos sin sesiones pegajosas.
- **Transferencia por streaming** (chunks de 1 MB) en vez de cargar
  archivos completos en memoria, pensando en archivos grandes.
- **Validación de rutas** en el servidor (`resolve()`) para prevenir path
  traversal fuera del directorio raíz de almacenamiento.
- **Protocol Buffers como IDL**: el mismo `.proto` será la base para
  extender el protocolo entre SuperPeers en la Opción 2
  (ControlNode↔ControlNode, ControlNode↔DataNode, DataNode↔DataNode).
- **Dockerizado desde el hito 1**: servidor y cliente corren en
  contenedores separados conectados por red Docker, anticipando el
  despliegue multi-nodo de los siguientes hitos.

---

## 8. Fuera de alcance en este hito

Se posponen intencionalmente para los siguientes hitos, cuando se
evolucione hacia la Opción 2 (P2P/SuperPeer):

- **RNF1 / RNF4** — escalabilidad y particionamiento de archivos entre
  múltiples nodos.
- **RNF2 / RNF3** — alta disponibilidad, redundancia y consistencia
  (réplica de datos y metadatos).
- **RNF6** — seguridad: cifrado en tránsito/reposo, autenticación
  (user/pass, ACL, 2FA, API Keys) y seguridad entre nodos.
- **RNF7** — transparencia total de localización (montaje tipo sistema de
  archivos local).