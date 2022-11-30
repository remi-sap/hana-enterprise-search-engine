FROM python:3.10-slim-bullseye

# Dockerfile to build an image with the latest main branch on git.
# !! The secrets must be in a file .config.json which is NOT present in the image
# !! The .config.json must be added at runtime:
# docker run -ti --mount type=bind,source=$(pwd)/src/.config.json,target=/home/appowner/hana-esh-odata/src/.config.json,readonly hana-esh 

LABEL "origin"="https://github.com/SAP-samples/hana-enterprise-search-engine"

LABEL org.opencontainers.image.source=https://github.com/remi-sap/hana-enterprise-search-engine

ENV APP_FOLDER=/home/appowner/hana-esh-odata

RUN addgroup --gid 1000 appowner \
    && adduser --disabled-login -q -u 1000 --gid 1000 appowner

USER appowner

WORKDIR ${APP_FOLDER}

#copy sources
RUN mkdir -p src static 
COPY --chown=1000:1000 ./src ./src/
COPY --chown=1000:1000 ./static ./static

#install python libraries 
COPY --chown=1000:1000 ./requirements/core.txt ./requirements.txt
RUN python3 -m pip install -r requirements.txt --no-cache-dir 

EXPOSE 8000

#CMD ["python3", "src/server.py"]
ENTRYPOINT ["python3", "src/server.py"]
