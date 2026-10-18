# Pinned so a reader reproduces the published numbers rather than their own.
# Note: timings taken inside a container on a shared host carry more variance
# than bare metal. The image exists for reproducible *compilation*; for
# trustworthy *timings*, run the harness directly on a quiet machine.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        clang-18 \
        llvm-18 \
        binutils \
        make \
        python3 \
        python3-matplotlib \
        linux-tools-generic \
    && rm -rf /var/lib/apt/lists/*

# Stable names, so the Makefile does not need to know the version suffix.
RUN ln -sf /usr/bin/clang-18 /usr/local/bin/clang \
 && ln -sf /usr/bin/clang++-18 /usr/local/bin/clang++

WORKDIR /work
COPY . /work

CMD ["make", "all"]
