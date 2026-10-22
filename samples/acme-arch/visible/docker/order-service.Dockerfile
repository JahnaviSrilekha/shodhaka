FROM eclipse-temurin:21.0.4_7-jre
WORKDIR /app
COPY build/libs/order-service.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
