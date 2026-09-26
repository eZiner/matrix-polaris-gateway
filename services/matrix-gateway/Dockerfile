# ==============================================================================
# STAGE 1: Der Builder (Kompilierung des Rust-Gateways)
# ==============================================================================
FROM rust:1.80-slim AS builder
WORKDIR /usr/src/matrix-polaris-gateway

# System-Abhängigkeiten installieren (inklusive OpenSSL und SQLite für Krypto)
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# 1. Dependency-Caching: Nur Cargo-Dateien kopieren und Dummy-Build ausführen
COPY Cargo.toml ./
RUN mkdir src && echo "fn main() {}" > src/main.rs
RUN cargo build --release
RUN rm -f target/release/deps/matrix_polaris_gateway*

# 2. Den echten Quellcode kopieren und die produktive Binärdatei bauen
COPY src ./src
RUN cargo build --release

# ==============================================================================
# STAGE 2: Der Runner (Die schlanke Laufzeitumgebung für das Rechenzentrum)
# ==============================================================================
FROM debian:bookworm-slim AS runner
WORKDIR /app

# Nur die absolut notwendigen Laufzeit-Bibliotheken installieren
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

# Die fertige, extrem optimierte Binärdatei aus Stage 1 rüberkopieren
COPY --from=builder /usr/src/matrix-polaris-gateway/target/release/matrix-polaris-gateway .

# Sicherheits-Best-Practice: Den Bot NIEMALS als 'root' ausführen!
RUN useradd -m -u 10001 polarisuser
USER polarisuser

# Startbefehl für den Docker-Container
CMD ["./matrix-polaris-gateway"]
