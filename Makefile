python=/usr/bin/env python
docker=/usr/bin/env docker
name=tubesync
image=$(name):latest


all: clean build


dev:
	$(python) tubesync/manage.py runserver


build:
	mkdir -p tubesync/media
	mkdir -p tubesync/static
	$(python) tubesync/manage.py collectstatic --noinput

migrate:
	$(python) tubesync/manage.py migrate

clean:
	rm -rf tubesync/static


container: clean
	$(docker) build -t $(image) .


runcontainer:
	@if [ "$(persist)" = "true" ]; then \
		$(docker) run --rm --name $(name) -v ./container_config:/config -v ./container_downloads:/downloads -v ./tubesync/sync/management/commands:/app/sync/management/commands --env-file dev.env --log-opt max-size=50m -ti -p 4848:4848 -d $(image); \
		$(MAKE) container_logs;\
	else \
		$(docker) run --rm --name $(name) --env-file dev.env --log-opt max-size=50m -ti -p 4848:4848 $(image);\
	fi

stopcontainer:
	-$(docker) stop $(name)

container_logs:
	$(docker) logs -f $(name)

container_exec:
	$(docker) exec -ti $(name) $(exec)

container_manage:
	$(docker) exec -ti $(name) python3 manage.py $(command)

test: build
	cd tubesync && $(python) manage.py test --verbosity=2 && cd ..

container_rebuild: stopcontainer container runcontainer

container_reset: stopcontainer container
	rm -rf container_config
	rm -rf container_downloads
	$(MAKE) runcontainer persist=$(persist)

shell:
	cd tubesync && $(python) manage.py shell
