# CD supplies the exact executable JAR produced by the successful CI run.
FROM eclipse-temurin:21-jre-jammy
WORKDIR /app
COPY --chown=1000:1000 target/*.jar app.jar
USER 1000:1000
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
