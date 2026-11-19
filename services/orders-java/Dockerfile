FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY pom.xml .
RUN mvn -q -DskipTests dependency:go-offline
COPY src ./src
RUN mvn -q -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
ARG OTEL_AGENT_VERSION=2.33.1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL "https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v${OTEL_AGENT_VERSION}/opentelemetry-javaagent.jar" -o /otel-javaagent.jar \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /workspace/target/orders-0.1.0.jar /app/orders.jar
EXPOSE 8080
ENTRYPOINT ["java", "-javaagent:/otel-javaagent.jar", "-jar", "/app/orders.jar"]
