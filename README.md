# PROYECTO DE ENCUESTAS

## 🐍 Requisitos

- Python 3.8 o superior instalado.
- `pip` (incluido con Python).
- Terminal o línea de comandos.

## ⚙️ Configuración del entorno virtual

Sigue estos pasos para configurar y activar el entorno virtual `.venv`:

### 1. **Clonar el repositorio**
   ```bash
   git clone https://github.com/BryanM518/Backend-Encuestas
   cd /Backend-Encuestas
   ```

### 1. Crear el entorno virtual

Ejecuta el siguiente comando en la raíz del proyecto:

```bash
python -m venv .venv


.venv\Scripts\activate

pip install -r requirements.txt

uvicorn main:app --reload
```