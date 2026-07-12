.PHONY: help seed seed-in-docker seed-host docker-up docker-down logs reseed clean

COMPOSE ?= docker compose

help:
	@echo "Loomi dev shortcuts"
	@echo "  make docker-up        - start the full docker stack"
	@echo "  make seed             - seed inside loomi-core (writes to the Chroma the backend reads)"
	@echo "  make seed-host        - seed on the host (uses local Chroma; only useful if NOT running docker)"
	@echo "  make reseed           - stop chroma container (and force a clean reseed on next up)"
	@echo "  make logs             - tail logs from the core service"
	@echo "  make clean            - stop stack + remove named volumes (DESTROYS DATA)"

docker-up:
	$(COMPOSE) up -d --build

docker-down:
	$(COMPOSE) down

seed: seed-in-docker

seed-in-docker:
	@docker exec loomi-core python -m db.seed

seed-host:
	@python -m db.seed

reseed: seed-in-docker

logs:
	$(COMPOSE) logs -f core

clean:
	$(COMPOSE) down -v
