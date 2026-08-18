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
    && find /root/.m2/repository -name "maven-metadata-local.xml" -type f -delete 2>/dev/null || true \
    && mvn -s /tmp/settings.xml clean package -DskipTests -pl "$MODULE" -am' \
    && mkdir /output \
    && find "${MODULE}/target" -maxdepth 1 -name '*.jar' ! -name '*.original' -exec cp {} /output/app.jar \;

FROM ${JRE_IMAGE}
WORKDIR /app
# 健康检查需要使用 curl 访问 Spring Boot 的业务接口，确保容器启动不仅代表 Java 进程存在，
# 还代表 Tomcat 已经监听端口并能够处理请求。
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /output/app.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
