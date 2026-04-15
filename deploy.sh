#!/bin/bash
set -e

echo "========================================="
echo "  Rayna Product Automation - EC2 Deploy"
echo "========================================="

# ── Step 1: Install Docker ──────────────────
install_docker() {
    echo "[1/6] Installing Docker..."
    sudo apt update && sudo apt upgrade -y
    sudo apt install -y ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt update
    sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo usermod -aG docker $USER
    echo "Docker installed. You may need to logout/login for group changes."
}

# ── Step 2: Clone repos ────────────────────
clone_repos() {
    echo "[2/6] Cloning repositories..."
    mkdir -p ~/apps && cd ~/apps

    if [ ! -d "backend" ]; then
        read -p "Enter backend repo URL: " BACKEND_REPO
        git clone "$BACKEND_REPO" backend
    else
        echo "  Backend repo already exists, pulling latest..."
        cd backend && git pull && cd ..
    fi

    if [ ! -d "frontend" ]; then
        read -p "Enter frontend repo URL: " FRONTEND_REPO
        git clone "$FRONTEND_REPO" frontend-repo
        # The frontend code is inside frontend-repo/frontend/
    else
        echo "  Frontend repo already exists, pulling latest..."
        cd frontend-repo && git pull && cd ..
    fi
}

# ── Step 3: Setup env file ─────────────────
setup_env() {
    echo "[3/6] Setting up environment..."
    cd ~/apps/backend

    if [ ! -f ".env" ]; then
        cp .env.docker .env
        echo ""
        echo "  IMPORTANT: Edit ~/apps/backend/.env with your actual values!"
        echo "  Run: nano ~/apps/backend/.env"
        echo ""
        read -p "  Press Enter after you've edited .env..."
    else
        echo "  .env already exists."
    fi
}

# ── Step 4: Update frontend path in .env ───
update_frontend_path() {
    echo "[4/6] Updating frontend path..."
    cd ~/apps/backend
    # Set the frontend path relative to docker-compose location
    sed -i "s|FRONTEND_PATH=.*|FRONTEND_PATH=../frontend-repo/frontend|" .env
}

# ── Step 5: Build & Start ─────────────────
start_services() {
    echo "[5/6] Building and starting all services..."
    cd ~/apps/backend
    docker compose up -d --build
    echo "  Waiting for services to be healthy..."
    sleep 10
}

# ── Step 6: Run migrations ─────────────────
run_migrations() {
    echo "[6/6] Running database migrations..."
    cd ~/apps/backend
    docker compose exec backend alembic upgrade head
    echo ""
    echo "========================================="
    echo "  Deployment Complete!"
    echo "========================================="
    echo ""
    EC2_IP=$(grep EC2_PUBLIC_IP .env | cut -d '=' -f2)
    echo "  Frontend:  http://$EC2_IP"
    echo "  API:       http://$EC2_IP/api/v1"
    echo "  API Docs:  http://$EC2_IP/docs"
    echo "  Health:    http://$EC2_IP/health"
    echo ""
    docker compose ps
}

# ── Run all steps ──────────────────────────
case "${1:-all}" in
    docker)     install_docker ;;
    clone)      clone_repos ;;
    env)        setup_env ;;
    build)      start_services ;;
    migrate)    run_migrations ;;
    all)
        install_docker
        clone_repos
        setup_env
        update_frontend_path
        start_services
        run_migrations
        ;;
    *)
        echo "Usage: $0 {docker|clone|env|build|migrate|all}"
        exit 1
        ;;
esac
