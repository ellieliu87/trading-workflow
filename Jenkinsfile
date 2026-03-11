// Trading Workflow — Jenkins Declarative Pipeline
// Stages: Install → Lint → Type Check → Test → Build → Deploy
// Deploy runs only on the `main` branch.

pipeline {

    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    environment {
        // Resolve uv binary location after installation
        UV        = "${isUnix() ? "${HOME}/.local/bin/uv" : "${USERPROFILE}\\.local\\bin\\uv.exe"}"
        // Secrets — configure these in Jenkins → Manage Credentials
        OPENAI_API_KEY       = credentials('openai-api-key')
        // Disable Phoenix tracing in CI (no local server available)
        PHOENIX_ENABLED      = 'false'
    }

    stages {

        // ------------------------------------------------------------------ //
        stage('Checkout') {
            steps {
                checkout scm
                echo "Branch: ${env.BRANCH_NAME} | Build: ${env.BUILD_NUMBER} | Commit: ${env.GIT_COMMIT?.take(8)}"
            }
        }

        // ------------------------------------------------------------------ //
        stage('Install uv') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            if ! command -v uv &> /dev/null; then
                                echo "Installing uv..."
                                curl -LsSf https://astral.sh/uv/install.sh | sh
                            else
                                echo "uv already installed: $(uv --version)"
                            fi
                        '''
                    } else {
                        powershell '''
                            if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
                                Write-Host "Installing uv..."
                                irm https://astral.sh/uv/install.ps1 | iex
                            } else {
                                Write-Host "uv already installed: $(uv --version)"
                            }
                        '''
                    }
                }
            }
        }

        // ------------------------------------------------------------------ //
        stage('Install Dependencies') {
            steps {
                script {
                    if (isUnix()) {
                        sh '$UV sync --all-groups --frozen'
                    } else {
                        bat '%UV% sync --all-groups --frozen'
                    }
                }
            }
        }

        // ------------------------------------------------------------------ //
        stage('Lint') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            $UV run ruff format --check .
                            $UV run ruff check .
                        '''
                    } else {
                        bat '''
                            %UV% run ruff format --check .
                            %UV% run ruff check .
                        '''
                    }
                }
            }
            post {
                failure {
                    echo 'Lint failed. Run "uv run ruff format . && uv run ruff check . --fix" locally to fix.'
                }
            }
        }

        // ------------------------------------------------------------------ //
        stage('Type Check') {
            steps {
                script {
                    if (isUnix()) {
                        sh '$UV run mypy .'
                    } else {
                        bat '%UV% run mypy .'
                    }
                }
            }
            post {
                failure {
                    echo 'Type check failed. Review mypy output above and add missing annotations.'
                }
            }
        }

        // ------------------------------------------------------------------ //
        stage('Test') {
            environment {
                // Use a temp dir for workflow state files created during tests
                WORKFLOW_STATE_DIR = "${env.WORKSPACE}/tmp/workflow_states"
            }
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            mkdir -p tmp/workflow_states
                            $UV run pytest tests/unit \
                                --junitxml=reports/junit.xml \
                                --cov=. \
                                --cov-report=xml:reports/coverage.xml \
                                --cov-report=html:reports/htmlcov \
                                --cov-fail-under=70 \
                                -v
                        '''
                    } else {
                        powershell '''
                            New-Item -ItemType Directory -Force -Path tmp\workflow_states | Out-Null
                            & $env:UV run pytest tests\unit `
                                --junitxml=reports\junit.xml `
                                --cov=. `
                                --cov-report=xml:reports\coverage.xml `
                                --cov-report=html:reports\htmlcov `
                                --cov-fail-under=70 `
                                -v
                        '''
                    }
                }
            }
            post {
                always {
                    // Publish JUnit test results
                    junit allowEmptyResults: true, testResults: 'reports/junit.xml'
                    // Publish HTML coverage report
                    publishHTML(target: [
                        allowMissing         : true,
                        alwaysLinkToLastBuild: true,
                        keepAll              : true,
                        reportDir            : 'reports/htmlcov',
                        reportFiles          : 'index.html',
                        reportName           : 'Coverage Report',
                    ])
                    // Archive XML coverage for downstream tools (e.g. SonarQube)
                    archiveArtifacts artifacts: 'reports/coverage.xml', allowEmptyArchive: true
                }
            }
        }

        // ------------------------------------------------------------------ //
        stage('Build') {
            steps {
                script {
                    if (isUnix()) {
                        sh '$UV build'
                    } else {
                        bat '%UV% build'
                    }
                }
            }
            post {
                success {
                    archiveArtifacts artifacts: 'dist/*.whl, dist/*.tar.gz', fingerprint: true
                }
            }
        }

        // ------------------------------------------------------------------ //
        stage('Deploy') {
            // Only deploy from the main branch
            when {
                branch 'main'
                beforeAgent true
            }
            steps {
                script {
                    echo "Deploying build ${env.BUILD_NUMBER} from commit ${env.GIT_COMMIT?.take(8)}..."
                    if (isUnix()) {
                        sh '''
                            # ---------- Option A: install wheel to system / shared venv ----------
                            # Uncomment and adjust DEPLOY_TARGET_VENV to match your environment.
                            # DEPLOY_TARGET_VENV="/opt/trading-workflow/venv"
                            # $DEPLOY_TARGET_VENV/bin/pip install --force-reinstall dist/*.whl

                            # ---------- Option B: rsync source to remote host ----------
                            # rsync -avz --exclude='.venv' --exclude='dist' --exclude='tmp' \
                            #     ./ deploy_user@deploy-host:/opt/trading-workflow/

                            # ---------- Option C: copy wheel to shared artifact store ----------
                            # cp dist/*.whl /mnt/releases/trading-workflow/

                            echo "Deploy step placeholder — configure one of the options above."
                        '''
                    } else {
                        powershell '''
                            # ---------- Option A: install wheel to system / shared venv ----------
                            # $deployVenv = "C:\\opt\\trading-workflow\\venv"
                            # & "$deployVenv\\Scripts\\pip.exe" install --force-reinstall (Get-Item dist\\*.whl)

                            # ---------- Option B: copy wheel to shared network path ----------
                            # Copy-Item dist\\*.whl -Destination "\\\\fileserver\\releases\\trading-workflow\\"

                            Write-Host "Deploy step placeholder - configure one of the options above."
                        '''
                    }
                }
            }
        }

    }

    // ---------------------------------------------------------------------- //
    post {

        always {
            // Clean up temp state files generated during tests
            script {
                if (isUnix()) {
                    sh 'rm -rf tmp/'
                } else {
                    powershell 'Remove-Item -Recurse -Force tmp\\ -ErrorAction SilentlyContinue'
                }
            }
        }

        success {
            echo "Pipeline succeeded — Build #${env.BUILD_NUMBER} on ${env.BRANCH_NAME}."
        }

        failure {
            echo "Pipeline FAILED — Build #${env.BUILD_NUMBER} on ${env.BRANCH_NAME}. Check stage logs above."
            // Uncomment to send email notifications:
            // mail to: 'team@yourorg.com',
            //      subject: "FAILED: Trading Workflow Build #${env.BUILD_NUMBER}",
            //      body: "Branch: ${env.BRANCH_NAME}\nCommit: ${env.GIT_COMMIT}\nSee: ${env.BUILD_URL}"
        }

        unstable {
            echo "Pipeline UNSTABLE — some tests may have failed. Review test report."
        }

        cleanup {
            cleanWs()
        }

    }
}
