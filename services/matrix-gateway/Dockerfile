# ==============================================================================
# STAGE 1: Der Builder (Kompilierung mit modernem BuildKit-Cache)
# ==============================================================================
FROM rust:1.96-slim AS builder
WORKDIR /usr/src/matrix-polaris-gateway

# System-Abhängigkeiten für OpenSSL und SQLite installieren
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# Gesamten Kontext kopieren (Cargo.toml und src-Ordner auf einmal)
COPY . .

# Modernes Caching aktivieren: Verhindert das ständige Neuladen aus dem Internet
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/src/matrix-polaris-gateway/target \
    cargo build --release && \
    cp target/release/matrix-polaris-gateway /usr/src/matrix-polaris-gateway/polaris-app

# ==============================================================================
# STAGE 2: Der Runner (Die schlanke Laufzeitumgebung für das Rechenzentrum)
# ==============================================================================
FROM debian:trixie-slim AS runner
WORKDIR /app

# Notwendige Laufzeit-Bibliotheken installieren
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

# Die eindeutig zwischengespeicherte Binärdatei rüberkopieren
COPY --from=builder /usr/src/matrix-polaris-gateway/polaris-app ./matrix-polaris-gateway

# Sicherheits-Best-Practice: Nicht als root ausführen
RUN useradd -m -u 10001 polarisuser
USER polarisuser

# Startbefehl
CMD ["./matrix-polaris-gateway"]
