# ==========================================
# STAGE 1: Der Builder (Kompilierung)
# ==========================================
FROM rust:1.75-slim AS builder

WORKDIR /usr/src/matrix-polaris-gateway

# System-Abhängigkeiten für den Build-Prozess installieren (z. B. für TLS/Krypto)
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 1. Trick für schnelleres Docker-Caching: Erst nur die Abhängigkeiten kompilieren
COPY Cargo.toml ./
RUN mkdir src && echo "fn main() {}" > src/main.rs
RUN cargo build --release
RUN rm -f target/release/deps/matrix_polaris_gateway*

# 2. Den echten Quellcode kopieren und die produktive Binärdatei bauen
COPY src ./src
RUN cargo build --release

# ==========================================
# STAGE 2: Der Runner (Die schlanke Laufzeitumgebung)
# ==========================================
FROM debian:bookworm-slim AS runner

WORKDIR /app

# Nur die absolut notwendigen Laufzeit-Bibliotheken für SSL/TLS nachinstallieren
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Die fertige, extrem optimierte Binärdatei aus der ersten Stage rüberkopieren
COPY --from=builder /usr/src/matrix-polaris-gateway/target/release/matrix-polaris-gateway .

# Sicherheits-Best-Practice: Den Bot NIEMALS als 'root' ausführen!
# Wir erstellen einen unprivilegierten System-User.
RUN useradd -m -u 10001 polarisuser
USER polarisuser

# Startbefehl für den Docker-Container
CMD ["./matrix-polaris-gateway"]
