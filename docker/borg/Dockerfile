FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y \
    openssh-server borgbackup \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir /var/run/sshd && mkdir -p /data/borg
RUN useradd -m -d /home/borg -s /bin/bash borg
EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
