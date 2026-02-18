/**
 * PM2 ecosystem config for Punter Punter Punter Bot
 *
 * Manages both the Node.js WhatsApp bridge and the Python Flask backend.
 * Run from project root: pm2 start ecosystem.config.js
 */

module.exports = {
  apps: [
    {
      name: "punter-bridge",
      script: "index.js",
      cwd: "./bridge",
      interpreter: "node",
      // Bridge must start first so Flask can reach it; Flask retries on 503
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      env: {
        NODE_ENV: "production",
      },
      error_file: "../logs/bridge-error.log",
      out_file: "../logs/bridge-out.log",
      merge_logs: true,
    },
    {
      name: "punter-flask",
      script: "src/app.py",
      cwd: "./",
      interpreter: "./venv/bin/python",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "300M",
      env: {
        FLASK_DEBUG: "false",
        FLASK_ENV: "production",
        PYTHONPATH: ".",
      },
      error_file: "./logs/flask-error.log",
      out_file: "./logs/flask-out.log",
      merge_logs: true,
    },
    {
      name: "punter-health-check",
      script: "scripts/health_check.py",
      cwd: "./",
      interpreter: "./venv/bin/python",
      instances: 1,
      autorestart: true,
      watch: false,
      env: {
        FLASK_URL: "http://127.0.0.1:5001",
        HEALTH_CHECK_INTERVAL: "300",
      },
      error_file: "./logs/health-check-error.log",
      out_file: "./logs/health-check-out.log",
      merge_logs: true,
    },
  ],
};
