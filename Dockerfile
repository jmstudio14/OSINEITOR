# Imagen mínima de OSINEITOR: se construye el wheel y solo él pasa a la imagen final,
# que corre sin privilegios.
#
#   docker build -t osineitor .
#   docker run --rm -v osineitor-data:/data osineitor domain example.com
#
# Las API keys van por variables de entorno (-e OSINEITOR_SHODAN_KEY=...). Los scans, la caché y
# los informes exportados quedan en el volumen /data.

FROM python:3.13-slim AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir build && python -m build --wheel --outdir /dist

FROM python:3.13-slim
RUN useradd --create-home --uid 10001 osineitor \
    && mkdir /data \
    && chown osineitor /data
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
USER osineitor
ENV OSINEITOR_DATA_DIR=/data \
    OSINEITOR_CONFIG_DIR=/home/osineitor/.config/osineitor \
    PYTHONUNBUFFERED=1
WORKDIR /data
VOLUME /data
ENTRYPOINT ["osineitor"]
CMD ["--help"]
