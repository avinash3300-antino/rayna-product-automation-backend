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

    BACKEND_REPO="https://github.com/avinash3300-antino/rayna-product-automation-backend.git"
    FRONTEND_REPO="https://github.com/avinash3300-antino/rayna-product-automation-frontend.git"

    if [ ! -d "backend" ]; then
        git clone "$BACKEND_REPO" backend
    else
        echo "  Backend repo already exists, pulling latest..."
        cd backend && git pull && cd ..
    fi

    if [ ! -d "frontend-repo" ]; then
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
    echo "  Migrations complete."
}

# ── Step 7: Seed admin user ───────────────
seed_db() {
    echo "[7] Seeding admin user..."
    cd ~/apps/backend
    docker compose exec backend python seed.py
    echo "  Seed complete."
}

# ── Step 8: Restore local data ────────────
restore_data() {
    echo "[8] Restoring database from dump..."
    cd ~/apps/backend
    if [ -f "rayna_db_dump.sql" ]; then
        PGPASSWORD=$(grep POSTGRES_PASSWORD .env | cut -d '=' -f2)
        docker compose exec -T postgres psql -U postgres -d rayna_db < rayna_db_dump.sql
        echo "  Data restored."
    else
        echo "  No rayna_db_dump.sql found. Skipping restore."
        echo "  Upload it with: scp rayna_db_dump.sql ubuntu@EC2_IP:~/apps/backend/"
    fi
}

show_info() {
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
    echo "  Login:     admin@raynatours.com / Admin@1234"
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
    seed)       seed_db ;;
    restore)    restore_data ;;
    all)
        install_docker
        clone_repos
        setup_env
        update_frontend_path
        start_services
        run_migrations
        seed_db
        show_info
        ;;
    *)
        echo "Usage: $0 {docker|clone|env|build|migrate|seed|restore|all}"
        exit 1
        ;;
esac
