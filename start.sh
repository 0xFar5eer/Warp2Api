#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}     Warp2Api Docker Startup Script      ${NC}"
echo -e "${BLUE}=========================================${NC}"

# Function to check if a command exists
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}✗ $1 is not installed${NC}"
        return 1
    else
        echo -e "${GREEN}✓ $1 is installed${NC}"
        return 0
    fi
}

# Function to display installation instructions
show_install_instructions() {
    echo -e "\n${YELLOW}Installation Instructions:${NC}"
    
    # Detect OS
    OS="Unknown"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macOS"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="Linux"
    fi
    
    if [ "$1" == "docker" ] || [ "$1" == "docker-compose" ]; then
        echo -e "${YELLOW}Docker/Docker Compose is missing. Please install:${NC}"
        
        if [ "$OS" == "macOS" ]; then
            echo -e "  • Download Docker Desktop from: ${BLUE}https://www.docker.com/products/docker-desktop${NC}"
            echo -e "  • Or install via Homebrew: ${GREEN}brew install --cask docker${NC}"
        elif [ "$OS" == "Linux" ]; then
            echo -e "  • Ubuntu/Debian: ${GREEN}sudo apt-get update && sudo apt-get install docker.io docker-compose${NC}"
            echo -e "  • Fedora/RHEL: ${GREEN}sudo dnf install docker docker-compose${NC}"
            echo -e "  • Arch: ${GREEN}sudo pacman -S docker docker-compose${NC}"
            echo -e "  • Or follow: ${BLUE}https://docs.docker.com/engine/install/${NC}"
        else
            echo -e "  • Visit: ${BLUE}https://docs.docker.com/get-docker/${NC}"
        fi
    fi
    
    if [ "$1" == "curl" ]; then
        echo -e "${YELLOW}curl is missing. Please install:${NC}"
        
        if [ "$OS" == "macOS" ]; then
            echo -e "  • Install via Homebrew: ${GREEN}brew install curl${NC}"
        elif [ "$OS" == "Linux" ]; then
            echo -e "  • Ubuntu/Debian: ${GREEN}sudo apt-get install curl${NC}"
            echo -e "  • Fedora/RHEL: ${GREEN}sudo dnf install curl${NC}"
            echo -e "  • Arch: ${GREEN}sudo pacman -S curl${NC}"
        fi
    fi
}

# Check prerequisites
echo -e "\n${YELLOW}Checking prerequisites...${NC}"
MISSING_DEPS=false

if ! check_command docker; then
    MISSING_DEPS=true
    show_install_instructions "docker"
fi

if ! check_command docker-compose; then
    MISSING_DEPS=true
    show_install_instructions "docker-compose"
fi

if ! check_command curl; then
    MISSING_DEPS=true
    show_install_instructions "curl"
fi

if [ "$MISSING_DEPS" == "true" ]; then
    echo -e "\n${RED}Please install missing dependencies and run this script again.${NC}"
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "\n${YELLOW}Creating .env file from .env.example...${NC}"
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${GREEN}✓ Created .env file${NC}"
        echo -e "${YELLOW}Please edit .env file to configure your settings${NC}"
    else
        echo -e "${RED}✗ .env.example not found. Please create .env file manually${NC}"
        exit 1
    fi
fi

# Stop all running containers
echo -e "\n${YELLOW}Stopping Docker Compose services...${NC}"
docker-compose down

# Force rebuild without cache
echo -e "\n${YELLOW}Force rebuilding Docker image (no cache)...${NC}"
docker-compose build --no-cache

# Check if build was successful
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Docker image rebuilt successfully${NC}"
else
    echo -e "${RED}✗ Docker build failed. Please check the errors above.${NC}"
    exit 1
fi

# Start services
echo -e "\n${YELLOW}Starting Docker Compose services...${NC}"
docker-compose up -d

# Check if services started
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Docker services started successfully${NC}"
else
    echo -e "${RED}✗ Failed to start Docker services${NC}"
    exit 1
fi

# Wait for health checks
echo -e "\n${YELLOW}Waiting for services to be healthy...${NC}"
max_attempts=60
attempt=0

while [ $attempt -lt $max_attempts ]; do
    # Check health on both ports
    health_4009=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:4009/healthz" 2>/dev/null)
    health_4010=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:4010/healthz" 2>/dev/null)
    
    if [ "$health_4009" == "200" ] && [ "$health_4010" == "200" ]; then
        echo -e "${GREEN}✓ All services are healthy and ready!${NC}"
        break
    fi
    
    attempt=$((attempt + 1))
    echo -ne "\rWaiting for services... ($attempt/$max_attempts seconds)"
    sleep 1
done

if [ $attempt -eq $max_attempts ]; then
    echo -e "\n${RED}✗ Services failed to become healthy after $max_attempts seconds${NC}"
    echo -e "${YELLOW}Port 4009 status: $health_4009${NC}"
    echo -e "${YELLOW}Port 4010 status: $health_4010${NC}"
    echo -e "${YELLOW}You can check logs with: docker-compose logs${NC}"
    exit 1
fi

# Display service information
echo -e "\n${GREEN}=========================================${NC}"
echo -e "${GREEN}       Services are running!             ${NC}"
echo -e "${GREEN}=========================================${NC}"
echo -e "• Protobuf API: ${BLUE}http://localhost:4009${NC}"
echo -e "• OpenAI API:   ${BLUE}http://localhost:4010${NC}"
echo -e ""
echo -e "${YELLOW}Useful commands:${NC}"
echo -e "• View logs:     ${GREEN}docker-compose logs -f${NC}"
echo -e "• Stop services: ${GREEN}docker-compose down${NC}"
echo -e "• Restart:       ${GREEN}docker-compose restart${NC}"
echo -e ""

# Check API_KEY configuration
API_KEY=$(grep "^API_KEY=" .env | cut -d'=' -f2)
if [ -z "$API_KEY" ]; then
    echo -e "${YELLOW}Note: API_KEY is empty - no authentication required${NC}"
else
    echo -e "${YELLOW}Note: API_KEY is set - authentication required${NC}"
    echo -e "      Use header: ${GREEN}X-API-Key: $API_KEY${NC}"
fi

echo -e "${GREEN}=========================================${NC}"