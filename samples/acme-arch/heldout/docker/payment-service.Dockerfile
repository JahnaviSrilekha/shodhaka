FROM eclipse-temurin
WORKDIR /app
COPY build/libs/payment-service.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
