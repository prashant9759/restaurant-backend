from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
import pytz
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.DEBUG)

jobstores = {
    'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')
}

# Scheduler setup
scheduler = BackgroundScheduler(daemon=True)  # ✅ Ensures it runs in the background
scheduler.configure(timezone=pytz.utc)


