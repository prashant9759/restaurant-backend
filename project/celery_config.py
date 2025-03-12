from celery import Celery 

def make_celery(app):
    celery = Celery(app.import_name)
    celery.conf.update(app.config["CELERY_CONFIG"])
    
    # Fix for Celery tasks stuck in PENDING state
    celery.conf.update(
        task_ignore_result=False,  # Store task results
        track_started=True,        # Track when a task starts
        accept_content=['json'],   # Ensure JSON serialization
        result_expires=3600        # Optional: Task results expire after 1 hour
    )
    
    class ContextTask(celery.Task):
        def __call__(self,*args,**kwargs):
            with app.app_context():
                return self.run(*args,**kwargs)


    celery.Task = ContextTask
    return celery