#!/bin/bash
# Quick start script for Reliable Prediction Framework

echo "=== Reliable Prediction Framework - Local Startup ==="
echo ""

# Check if PostgreSQL is running
if command -v pg_isready &> /dev/null; then
    if pg_isready > /dev/null 2>&1; then
        echo "✓ PostgreSQL is running"
    else
        echo "✗ PostgreSQL is not running. Please start it first:"
        echo "  brew services start postgresql  # macOS"
        echo "  sudo systemctl start postgresql  # Linux"
        exit 1
    fi
else
    echo "⚠ PostgreSQL not found. Please install it first."
    exit 1
fi

# Check if .env exists
if [ ! -f .env ]; then
    echo "✗ .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo "Please edit .env with your database configuration."
    exit 1
fi

echo "✓ Environment configuration found"
echo ""

# Check if database exists
if psql -lqt | cut -d \| -f 1 | grep -qw reliable_prediction; then
    echo "✓ Database 'reliable_prediction' exists"
else
    echo "✗ Database 'reliable_prediction' not found. Creating it..."
    createdb reliable_prediction
    echo "✓ Database created"
    echo "Applying schema..."
    psql reliable_prediction -f db/schema.sql
    echo "✓ Schema applied"
fi

echo ""
echo "=== Starting Services ==="
echo ""

# Start backend and frontend in background
echo "Starting backend and frontend (Terminal 1)..."
npm run dev &
BACKEND_PID=$!

# Wait for backend to start
sleep 5

# Start ML service in background
echo "Starting ML service (Terminal 2)..."
npm run dev:ml &
ML_PID=$!

echo ""
echo "=== Services Started ==="
echo "Frontend:     http://localhost:5000"
echo "Backend API:  http://localhost:3001"
echo "ML Service:   http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for user to stop
trap "kill $BACKEND_PID $ML_PID 2>/dev/null; echo ''; echo 'Services stopped'; exit 0" INT TERM

wait
