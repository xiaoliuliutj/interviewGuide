# syntax=docker/dockerfile:1.7
FROM maven:3.9.9-eclipse-temurin-21 AS build

ARG MODULE
WORKDIR /build
COPY backend/pom.xml backend/pom.xml
COPY backend backend
WORKDIR /build/backend
RUN --mount=type=cache,target=/root/.m2 mvn -pl "${MODULE}" -am package -DskipTests \
    && mkdir /output \
    && find "${MODULE}/target" -maxdepth 1 -name '*.jar' ! -name '*.original' -exec cp {} /output/app.jar \;

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /output/app.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
