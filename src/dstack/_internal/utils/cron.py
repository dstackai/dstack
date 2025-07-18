from apscheduler.triggers.cron import CronTrigger


def validate_cron(cron_expr: str):
    CronTrigger.from_crontab(cron_expr)
