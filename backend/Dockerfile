# syntax=docker/dockerfile:1.7
ARG MAVEN_IMAGE=maven:3.9.9-eclipse-temurin-21
ARG JRE_IMAGE=eclipse-temurin:21-jre
FROM ${MAVEN_IMAGE} AS build

ARG MODULE
ARG MAVEN_MIRROR_URL=https://repo.maven.apache.org/maven2
WORKDIR /build
COPY backend/pom.xml backend/pom.xml
COPY backend backend
WORKDIR /build/backend
RUN --mount=type=cache,target=/root/.m2 sh -c 'printf "<settings><mirrors><mirror><id>deployment-mirror</id><mirrorOf>*</mirrorOf><url>%s</url></mirror></mirrors></settings>" "$MAVEN_MIRROR_URL" > /tmp/settings.xml \
    && mvn -s /tmp/settings.xml -pl "$MODULE" -am package -DskipTests' \
    && mkdir /output \
    && find "${MODULE}/target" -maxdepth 1 -name '*.jar' ! -name '*.original' -exec cp {} /output/app.jar \;

FROM ${JRE_IMAGE}
WORKDIR /app
COPY --from=build /output/app.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
