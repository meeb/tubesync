python=/usr/bin/env python
docker=/usr/bin/docker
name=tubesync
image=$(name):latest


all: clean build


dev:
	$(python) tubesync/manage.py runserver


build:
	mkdir -p tubesync/media
	mkdir -p tubesync/static
	$(python) tubesync/manage.py collectstatic --noinput


clean:
	rm -rf tubesync/static


container: clean
	$(docker) build -t $(image) .


runcontainer:
	$(docker) run --rm --name $(name) --env-file dev.env --log-opt max-size=50m -ti -p 4848:4848 $(image)


stopcontainer:
	$(docker) stop $(name)


test: build
	cd tubesync && $(python) manage.py test --verbosity=2 && cd ..


shell:
	cd tubesync && $(python) manage.py shell
