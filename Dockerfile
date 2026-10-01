FROM python:3.12-slim-bookworm AS pjsip-build
ARG PJSIP_VERSION=2.16
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential swig curl ca-certificates libssl-dev libopus-dev \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir setuptools==80.9.0 wheel==0.45.1
WORKDIR /build
RUN curl -fsSL "https://github.com/pjsip/pjproject/archive/refs/tags/${PJSIP_VERSION}.tar.gz" -o pjsip.tar.gz \
    && tar -xzf pjsip.tar.gz
WORKDIR /build/pjproject-${PJSIP_VERSION}
RUN CFLAGS=-fPIC CXXFLAGS=-fPIC ./configure --disable-sound --disable-video --disable-libwebrtc \
    && make dep && make -j2 \
    && make -C pjsip-apps/src/swig/python wheel \
    && mkdir /wheels && cp pjsip-apps/src/swig/python/dist/*.whl /wheels/

FROM python:3.12-slim-bookworm AS runtime
LABEL org.opencontainers.image.licenses="GPL-3.0-or-later"
RUN apt-get update && apt-get install -y --no-install-recommends libssl3 libopus0 libstdc++6 libespeak-ng1 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home controller \
    && mkdir /data /models && chown controller:controller /data
COPY --from=pjsip-build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
WORKDIR /app
COPY scripts/download_models.py /app/scripts/download_models.py
RUN python /app/scripts/download_models.py
COPY pyproject.toml ./
COPY LICENSE THIRD_PARTY.md ./
COPY src ./src
RUN pip install --no-cache-dir '.[voice]'
COPY scripts/smoke_runtime.py /app/scripts/smoke_runtime.py
COPY scripts/verify_speech.py /app/scripts/verify_speech.py
COPY scripts/remove_legacy_runtime.py /app/scripts/remove_legacy_runtime.py
COPY config.example.yaml /app/config.example.yaml
USER controller
ENV PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
ENTRYPOINT ["voice-home"]
CMD ["serve"]
