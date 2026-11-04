# Radar Bursátil

Tu plan de inversión mensual en dólares a largo plazo, en una web gratuita en **GitHub Pages**. Cada mes le decís cuánto tenés para invertir y te dice dónde ponerlo para que tu cartera se acerque a tu plan. Una **tarea programada de GitHub Actions** la actualiza de lunes a viernes a las 18:30 (hora argentina) y te avisa al celular.

**Funciona gratis y sin IA.** La IA es un agregado opcional: una revisión por mes que cuesta centavos.

## Qué hace

**Gratis, todos los días hábiles**
- **Aporte del mes:** escribís el monto y te dice en qué instrumento ponerlo. Cada aporte va al grupo que más lejos está de su porcentaje objetivo. Con menos de US$ 200 va a un solo instrumento, para no pagar varias comisiones mínimas. Así la cartera se equilibra sola, sin vender nada.
- **Tu cartera real:** registrás lo que compraste y ves cuánto vale, cuánto ganás o perdés y cómo va contra el plan.
- **Ideas temáticas** (tecnología e IA, salud y biotecnología, energía y Argentina): cada candidato tiene un puntaje de 0 a 100 que combina:
  - tendencia de 12 meses (30 %);
  - **fundamentos** de los balances presentados en la SEC de EE.UU. (30 %);
  - **técnico** (20 %);
  - tono de las **noticias** (20 %).
  
  Además se marcan las menciones de **fusiones y adquisiciones** y se cuentan las **patentes** de los últimos 12 meses.
- **Señales técnicas** de tu cartera y tu lista, **mercados del mundo** y **enlaces** a las bolsas.
- **Avisos al celular:**
  - el recordatorio del aporte, el día del mes que elijas, con la sugerencia;
  - los cambios de señal de lo que tenés;
  - las posibles fusiones;
  - las tesis en riesgo;
  - un resumen los viernes.

**Opcional, con IA, una vez por mes**
- Revisa cada empresa con criterio: fundamentos, sentimiento de mercado, fusiones, patentes y aprobaciones. Deja un veredicto (reforzar, mantener, vigilar, salir o evitar) con su tesis y opina sobre el aporte sugerido.

> El 10 % anual en dólares es un objetivo, no una garantía. Nada de esto es asesoramiento financiero.

---

## Puesta en marcha (unos 20 minutos)

### 1. Crear el repositorio
1. En [github.com](https://github.com), tocá **New repository** y ponele de nombre `radar-bursatil`.
2. Elegí **Public**. GitHub Pages es gratis solo en repositorios públicos, así que **cualquiera con el enlace puede ver tu cartera**. Si querés que sea privado, necesitás GitHub Pro.

### 2. Subir los archivos
1. Descomprimí el zip.
2. Tocá **Add file → Upload files**, arrastrá **todo el contenido** de la carpeta `radar-bursatil` y confirmá con **Commit changes**.
3. Revisá que se haya subido `.github/workflows/actualizar.yml`. Las carpetas que empiezan con punto a veces quedan ocultas. Si falta, andá a **Actions → New workflow → set up a workflow yourself**, ponele de nombre `actualizar.yml` y pegá el contenido del archivo.

### 3. Activar la web
**Settings → Pages**: en *Source* elegí **Deploy from a branch**, en *Branch* elegí **main** y la carpeta **/docs**, y guardá. La web queda en `https://TU-USUARIO.github.io/radar-bursatil/`.

### 4. Permitir que la tarea publique
**Settings → Actions → General → Workflow permissions** → **Read and write permissions** → guardar.

### 5. Cargar los secretos (todos opcionales)
**Settings → Secrets and variables → Actions → New repository secret**:

| Nombre | Para qué | Cómo conseguirlo | Costo |
|---|---|---|---|
| `NTFY_TOPIC` | Avisos al celular | Inventá un nombre raro, por ejemplo `radar-sol-7k2m9x` | Gratis |
| `SEC_CONTACTO` | Fundamentos de las empresas | Tu email: la SEC pide identificarse | Gratis |
| `PATENTSVIEW_API_KEY` | Patentes | Pedí una clave en [patentsview.org](https://patentsview.org) (sección API) | Gratis |
| `ANTHROPIC_API_KEY` | Revisión mensual con IA | [platform.claude.com](https://platform.claude.com/): creá una clave y cargá saldo | Centavos por mes |
| `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` | Avisos por Telegram | Creá un bot con @BotFather | Gratis |

Los secretos no se ven en el repositorio ni en la web. Si no cargás alguno, esa parte se omite y el resto funciona igual.

### 6. Recibir avisos
Instalá **ntfy** en el celular (Android o iPhone) y suscribite al nombre que pusiste en `NTFY_TOPIC`. Cualquiera que conozca ese nombre puede leer tus avisos, por eso conviene que sea raro.

### 7. Poder registrar compras desde la web
En GitHub, andá a tu foto → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**:
- *Repository access*: **Only select repositories** → `radar-bursatil`.
- *Permissions*: **Contents: Read and write** y **Actions: Read and write**.

Copiá el token y pegalo en la web, en **Ayuda → Token de GitHub**. Queda guardado solo en ese navegador. Sin el token igual podés registrar compras: la web te da la línea para pegar en `cartera.json`.

### 8. Primera ejecución
**Actions → Revisión diaria → Run workflow** con `forzar_recordatorio: true`. Tarda de 5 a 10 minutos. Si cargaste la clave de la IA, poné también `forzar_ia: true`.

---

## Personalizar tu plan (`config.json`)

- `perfil.aporte_mensual_usd`: tu aporte habitual. En la web podés escribir otro monto cualquier mes.
- `distribucion`: los grupos con su peso y sus candidatos. Por defecto es así:

| Grupo | Peso | Candidatos |
|---|---|---|
| Núcleo: acciones de EE.UU. | 45 % | SPY |
| Núcleo: tecnología amplia | 15 % | QQQ |
| Núcleo: países desarrollados | 7 % | EFA |
| Núcleo: mercados emergentes | 8 % | EEM |
| Temática: tecnología e IA | 10 % | MSFT, NVDA, GOOGL, AVGO |
| Temática: salud y biotecnología | 7 % | LLY, VRTX, ISRG, ABBV |
| Temática: energía y Argentina | 8 % | VIST, YPF, PAM, GGAL, MELI |

  Podés cambiar los pesos (no hace falta que sumen 100, se ajustan solos), sumar o sacar candidatos, o crear grupos nuevos. En los grupos temáticos, `"patentes": true` activa el conteo de patentes.
- `lista`: otros instrumentos que querés seguir con señales.
- `ia.activada`: `true` o `false`.
- `avisos.dia_recordatorio`: el día del mes del recordatorio del aporte (por defecto, el 1).
- `avisos.resumen`: `"semanal"` (los viernes), `"diario"` o `"nunca"`.

## Registrar compras

Anotá cada compra con el **monto en dólares** y el **precio en dólares** de la acción o el ETF original. Si compraste CEDEARs, usá el valor en dólares de lo que invertiste. La web completa el precio con el último cierre, y lo podés corregir.

## Costos

- GitHub, GitHub Pages, Yahoo Finance, SEC, Google Noticias, PatentsView y ntfy: **gratis**.
- IA (opcional): una revisión por mes, del orden de 10 a 40 centavos de dólar. Las preguntas que le hagas desde la web usan tu clave y cuestan centavos cada una.

## Bueno saber

- GitHub puede demorar la tarea programada unos minutos. La tarea no corre los fines de semana.
- Los datos de Yahoo Finance tienen demora. Algunos bonos argentinos no figuran.
- La SEC solo tiene balances de empresas que presentan en EE.UU. Los ETFs no tienen fundamentos.
- El tono de las noticias se calcula con palabras clave en los titulares: es una aproximación. La IA, si la activás, lee con más criterio.
- La cantidad de patentes indica actividad de innovación, no su valor. Por eso no entra en el puntaje.
- Para probar la lógica en tu computadora: `python -m unittest discover tests`. Algunas pruebas necesitan Node.js.

## Estructura

```
config.json            tu plan
cartera.json           tus compras y ventas
scripts/update.py      proceso diario
scripts/radar/         señales, puntajes, rotación, noticias, SEC, patentes, IA y avisos
docs/                  la web (GitHub Pages); docs/rotation.js calcula el aporte al instante
docs/data/             datos que genera el proceso diario
tests/                 pruebas
.github/workflows/     tarea programada
```

**Aviso:** todo es análisis automatizado. No es asesoramiento financiero ni garantiza rendimientos, e invertir implica riesgo de pérdida.
