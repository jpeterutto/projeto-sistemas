FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /app

COPY proto/ /app/proto/
COPY client-java/ /app/client-java/

WORKDIR /app/client-java
RUN mvn clean package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app/client-java/target/chat-client-1.0-jar-with-dependencies.jar /app/client.jar
CMD ["java", "-jar", "/app/client.jar"]
