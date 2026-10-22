FROM eclipse-temurin:latest
WORKDIR /app
COPY build/libs/billing-service.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
