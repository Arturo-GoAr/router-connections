# Router Connections

Inventario y monitoreo de la red local. Descubre qué hay conectado a tu red, lo
identifica y clasifica, registra desde cuándo está conectado cada dispositivo,
escanea sus puertos abiertos y permite abrir o cerrar puertos tanto en el router
(UPnP) como en el Firewall de Windows.

Todo el descubrimiento funciona **sin privilegios de administrador y sin
instalar Nmap, Npcap ni ninguna herramienta externa**.

## Qué hace

- **Topología**: distingue si tu equipo cuelga directamente del router principal
  o si hay un segundo router haciendo NAT por encima (doble NAT), y detecta si
  tu operador usa CGNAT.
- **Inventario**: barre la subred completa y lista todo lo que responde, con IP,
  MAC y fabricante.
- **Identificación**: resuelve nombres por mDNS/Bonjour, SSDP/UPnP, NetBIOS y
  DNS inverso.
- **Categorización**: clasifica cada dispositivo (router, módem, PC, TV,
  teléfono, impresora, NAS…) sumando indicios, y **explica en qué se basó**.
- **Historial**: registra sesiones de conexión, así que sabes desde cuándo está
  conectado cada dispositivo y cuándo se fue.
- **Puertos**: escaneo TCP por dispositivo con lectura de banners.
- **Gestión de puertos**: redirecciones en el router por UPnP IGD y reglas del
  Firewall de Windows.
- **Personalización**: alias, notas, etiquetas de colores y categoría manual.

## Cómo funciona el descubrimiento

La parte que más suele costar es descubrir hosts sin permisos elevados. Un ping
ICMP necesita un socket raw, que en Windows exige privilegios. La solución que
usa este proyecto es distinta:

> Se envía un datagrama **UDP a un puerto muerto** de cada IP de la subred. No
> importa que nadie conteste al UDP: para poder enviarlo, el sistema operativo
> tiene que resolver antes la MAC del destino, y eso dispara un **ARP request**.
> Los hosts vivos responden a nivel de capa 2 y quedan registrados en la tabla
> ARP, que después se lee. Enviar UDP no requiere privilegios.

Con esto, una `/24` completa se barre en unos 3 segundos sin ser administrador.

La clasificación funciona por **acumulación de indicios**: ninguna señal por sí
sola dice "esto es una TV", pero el fabricante de la MAC, un servicio mDNS, un
puerto abierto y el nombre del host juntos sí apuntan en una dirección. Cada
regla suma puntos a una categoría y aporta una explicación, y la interfaz
muestra tanto el resultado como el razonamiento. Cuando no hay indicios
suficientes, el dispositivo se marca como *desconocido* en vez de adivinar.

## Requisitos

- Python 3.11+
- Node.js 20+
- Windows 10/11 para la gestión del Firewall y el detalle de interfaces. El
  escaneo y UPnP funcionan también en Linux y macOS.

## Puesta en marcha

### Uso normal: un solo archivo

Doble clic en **`RouterConnections.bat`**. Eso es todo.

El lanzador pide permisos de administrador, prepara el entorno de Python la
primera vez, compila la interfaz si hace falta, arranca el servidor y abre el
navegador en `http://127.0.0.1:8000`.

Se ejecuta elevado porque **crear y borrar reglas del Firewall de Windows es lo
único que exige privilegios**. Si lo abres sin elevar, todo lo demás —escaneo,
inventario, UPnP— funciona igual; solo la pestaña del firewall queda en modo
lectura, y la propia interfaz lo indica.

La aplicación se sirve entera desde un único proceso y un único puerto: el
backend publica también el frontend compilado.

### Desarrollo

Para trabajar en el código conviene levantar los dos servidores por separado y
tener recarga en caliente. `start-dev.ps1` lo hace, o a mano:

#### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

La API queda en `http://127.0.0.1:8000` y su documentación interactiva en
`http://127.0.0.1:8000/docs`.

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

La interfaz queda en `http://localhost:5173`. El servidor de desarrollo hace
proxy de `/api` y `/ws` al backend, así que no hay que configurar CORS ni URLs.

### Configuración

Todo es opcional. Copia `backend/.env.example` a `backend/.env` para ajustar el
intervalo de barrido, desactivar la consulta de IP pública, etc.

### Pruebas

```bash
cd backend
.venv\Scripts\python -m pytest
```

## Arquitectura

```
RouterConnections.bat  Lanzador único: eleva, prepara el entorno y arranca
backend/
  app/
    main.py            Punto de entrada FastAPI; sirve también el frontend
    models.py          Tablas SQLite (dispositivos, sesiones, puertos, etiquetas)
    scanner/
      arp.py           Barrido de la subred vía sondeo UDP + tabla ARP
      netinfo.py       Interfaces, IP pública y análisis de topología
      discovery.py     mDNS, SSDP/UPnP, NetBIOS y DNS inverso
      portscan.py      Escaneo TCP asíncrono con lectura de banners
      classify.py      Motor de clasificación por indicios
      oui.py           Fabricante a partir de la MAC (catálogo del IEEE)
      orchestrator.py  Encadena el barrido y persiste el resultado
    services/
      upnp.py          Cliente UPnP IGD escrito a mano (SSDP + SOAP)
      firewall.py      Reglas del Firewall de Windows
    api/               Rutas REST y WebSocket
frontend/
  src/
    api/               Cliente tipado de la API
    components/        Panel, tarjetas de dispositivo, cajón de detalle
    hooks/             WebSocket con reconexión automática
```

El backend empuja los cambios por WebSocket, así que la interfaz se actualiza
sola durante un barrido sin hacer polling.

## Decisiones de seguridad

- **El firewall solo se toca a sí mismo**: la app crea las reglas dentro del
  grupo `RouterConnections` y se niega a borrar cualquier regla que no haya
  creado ella. No puede desarmar el firewall del sistema.
- **Validación estricta de puertos**: la especificación de puertos se interpola
  en un comando de PowerShell, así que se valida contra dígitos, comas y guiones
  antes de llegar ahí.
- **La base de datos no se sube**: contiene las MAC e IP de tu red real, así que
  `backend/data/` está en `.gitignore`.
- **Una sola petición externa**: solo se sale a internet para consultar la IP
  pública y actualizar el catálogo de fabricantes del IEEE. Ambas se pueden
  desactivar.

## Limitaciones conocidas

- **Perfil de red Público**: si Windows tiene tu red marcada como *Pública*, el
  firewall bloquea el descubrimiento y mDNS/SSDP/NetBIOS devuelven pocos
  nombres. La app lo detecta y lo avisa en la interfaz.
- **MAC aleatorias**: iOS y Android aleatorizan la MAC por privacidad. En esos
  casos el fabricante no se puede deducir y la app no lo inventa.
- **UPnP desactivado**: muchos routers domésticos vienen con UPnP apagado de
  fábrica. Sin él no se pueden gestionar redirecciones desde aquí.
- **CGNAT**: si tu operador usa CGNAT, abrir un puerto en tu router no lo hace
  accesible desde internet, porque la IP pública es compartida.
- **Un router en modo AP no se puede distinguir**: si un segundo router trabaja
  como punto de acceso en la misma subred, sus clientes son indistinguibles de
  los del router principal desde un host normal. Esa información solo la tiene
  el propio equipo de red.

## Aviso

Escanea únicamente redes propias o para las que tengas autorización explícita.

## Licencia

MIT
