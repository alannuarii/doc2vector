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
                sleep time: 5, unit: 'SECONDS'
                sh "curl -f http://localhost:${HOST_PORT}/api/health || (echo '❌ Healthcheck failed' && exit 1)"
                echo "✅ Application ${APP_NAME} successfully deployed and running on port ${HOST_PORT}!"
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
