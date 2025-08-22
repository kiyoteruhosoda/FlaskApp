from .celery_app import celery
import time

@celery.task(bind=True)
def dummy_long_task(self, x, y):
    # 擬似的に長時間処理をする
    time.sleep(5)
    return {"result": x + y}
