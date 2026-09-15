pipeline {
    agent any

    environment {
        APP_NAME        = 'doc2vector'
        IMAGE_NAME      = 'doc2vector:latest'
        HOST_PORT       = '3017'
        CONTAINER_PORT  = '8000'
        DOCKER_NETWORK  = 'qdrant-net'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build Docker Image') {
            steps {
                echo "🔨 Building Docker image ${IMAGE_NAME}..."
                sh "docker build -t ${IMAGE_NAME} ."
            }
        }

        stage('Deploy Container') {
            steps {
                withCredentials([file(credentialsId: 'doc2vector-env', variable: 'ENV_FILE')]) {
                    script {
                        echo "🛑 Stopping existing container (if running)..."
                        sh "docker stop ${APP_NAME} || true"
                        sh "docker rm ${APP_NAME} || true"

                        echo "🚀 Starting new container ${APP_NAME} on port ${HOST_PORT}:${CONTAINER_PORT} in network ${DOCKER_NETWORK}..."
                        sh """
                            docker run -d \
                                --name ${APP_NAME} \
                                --restart always \
                                --network ${DOCKER_NETWORK} \
                                -p ${HOST_PORT}:${CONTAINER_PORT} \
                                --env-file ${ENV_FILE} \
                                ${IMAGE_NAME}
                        """
                    }
                }
            }
        }

        stage('Health Check') {
            steps {
                echo "🩺 Verifying application health..."
                script {
                    def maxRetries = 6
                    def retryInterval = 5 // seconds
                    def success = false
                    
                    for (int i = 1; i <= maxRetries; i++) {
                        echo "Attempt ${i}/${maxRetries} to curl healthcheck endpoint..."
                        def status = sh(script: "docker exec ${APP_NAME} curl -sf http://localhost:${CONTAINER_PORT}/api/health", returnStatus: true)
                        if (status == 0) {
                            success = true
                            echo "✅ Application ${APP_NAME} successfully deployed and running on port ${HOST_PORT}!"
                            break
                        }
                        if (i < maxRetries) {
                            echo "Waiting ${retryInterval} seconds before next attempt..."
                            sleep time: retryInterval, unit: 'SECONDS'
                        }
                    }
                    
                    if (!success) {
                        echo "❌ Healthcheck failed after ${maxRetries} attempts. Fetching container logs:"
                        sh "docker logs ${APP_NAME} || true"
                        error "Application failed to start or pass healthcheck."
                    }
                }
            }
        }
    }

    post {
        always {
            echo "🧹 Cleaning up dangling images..."
            sh "docker image prune -f || true"
        }
        success {
            echo "🎉 Pipeline finished successfully!"
        }
        failure {
            echo "🚨 Pipeline failed. Please check the logs above."
        }
    }
}
