ifeq ($(wildcard /code),)
PYTHON=PYTHONPATH=$$PYTHONPATH:../.. python3
else
PYTHON=python3
endif

MANAGE_PY=$(PYTHON) manage.py

.PHONY:
makemigrations:
	$(MANAGE_PY) makemigrations

.PHONY:
migrate:
	$(MANAGE_PY) migrate

.PHONY:
runserver:
	$(MANAGE_PY) runserver 0.0.0.0:8000
