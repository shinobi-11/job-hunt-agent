"""Route Django's internal tables (auth, sessions) to a separate sqlite file,
so our shared jobs.db stays clean of Django meta tables."""


class DjangoMetaRouter:
    DJANGO_APPS = {"auth", "contenttypes", "sessions", "admin", "messages"}

    def db_for_read(self, model, **hints):
        if model._meta.app_label in self.DJANGO_APPS:
            return "django_meta"
        return "default"

    def db_for_write(self, model, **hints):
        if model._meta.app_label in self.DJANGO_APPS:
            return "django_meta"
        return "default"

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in self.DJANGO_APPS:
            return db == "django_meta"
        if app_label == "app":
            return False
        return None
