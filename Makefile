python=/usr/bin/env python
docker=/usr/bin/docker
name=tubesync
image=$(name):latest


all: clean build


dev:
	$(python) app/manage.py runserver


build:
	mkdir -p app/media
	mkdir -p app/static
	$(python) app/manage.py collectstatic --noinput


clean:
	rm -rf app/static


container: clean
	$(docker) build -t $(image) .


runcontainer:
	$(docker) run --rm --name $(name) --env-file dev.env --log-opt max-size=50m -ti -p 4848:4848 $(image)


test:
	cd tubesync && $(python) manage.py test --verbosity=2 && cd ..
