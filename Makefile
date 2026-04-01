docker=/usr/bin/env docker
python=/usr/bin/env python
uv=/usr/bin/env uv

name=tubesync
image=$(name):latest


all: | clean build
css: tailwindcss | tubesync/common/static/styles/tailwind/tubesync-compiled.css
requirements: | requirements.txt requirements-dev.txt
.PHONY: all css requirements


dev:
	$(python) tubesync/manage.py runserver


css-watch:
	./tailwindcss --input tubesync/common/static/styles/tailwind/tubesync.css --output tubesync/common/static/styles/tailwind/tubesync-compiled.css --watch


build: | css
	mkdir -p tubesync/media
	mkdir -p tubesync/static
	$(python) tubesync/manage.py collectstatic --noinput


clean:
	rm -rf tubesync/static
.PHONY: clean


container: | clean
	$(docker) build -t $(image) .


runcontainer:
	$(docker) run --rm --name $(name) --env-file dev.env --log-opt max-size=50m -ti -p 4848:4848 $(image)


stopcontainer:
	$(docker) stop $(name)


test: | build
	cd tubesync && $(python) manage.py test --verbosity=2 && cd ..


shell:
	cd tubesync && $(python) manage.py shell

requirements.txt requirements-dev.txt: Pipfile
	$(uv) --no-config --no-managed-python --no-progress tool run pipenv requirements --no-lock $(if $(findstring -dev.txt,$@),--dev-only,) > $@

clean-requirements:
	rm -f requirements.txt requirements-dev.txt

.PHONY: clean-requirements
clean: | clean-requirements

rwildcard=$(foreach d,$(wildcard $(1:=/*)),$(call rwildcard,$d,$2) $(filter $(subst *,%,$2),$d))

APP_CSS = $(call rwildcard,tubesync,*.css)

TAILWIND_SRCS := $(foreach f, $(filter-out %-compiled.css, $(APP_CSS)), \
    $(if $(filter %/tailwind/, $(dir $(f))), $(f)))

$(TAILWIND_SRCS:.css=-compiled.css): %-compiled.css: %.css
	./tailwindcss --input $< --output $@

clean-tailwind:
	rm -f $(TAILWIND_SRCS:.css=-compiled.css)

.PHONY: clean-tailwind
clean: | clean-tailwind
