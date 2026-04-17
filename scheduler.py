import schedule
import time
import datetime
import logging
from app.main import post_to_sl

# Configuración básica de logging para ver los eventos en la consola
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def scheduled_job():
    """
    La tarea que se ejecutará según el horario programado.
    """
    # Verificamos si el día actual es de Lunes (0) a Sábado (5)
    if datetime.datetime.today().weekday() < 6:
        logging.info("Iniciando tarea programada...")
        try:
            # Llamamos a la función principal de tu aplicación
            post_to_sl()
            logging.info("La tarea finalizó exitosamente.")
        except Exception as e:
            logging.error(f"Ocurrió un error durante la ejecución de la tarea: {e}", exc_info=True)
    else:
        logging.info("Tarea omitida (es domingo).")

def doing():
    print("hola")
    
# Programamos la tarea para que se ejecute cada 5 minutos
schedule.every(5).minutes.do(scheduled_job)

logging.info("Scheduler iniciado. El script se está ejecutando...")

# Bucle principal para mantener el script corriendo y verificar tareas pendientes
if __name__ == "__main__":
    while True:
        schedule.run_pending()
        time.sleep(1)
