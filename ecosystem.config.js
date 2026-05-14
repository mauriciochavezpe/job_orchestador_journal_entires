// ecosystem.config.js
module.exports = {
    apps: [
        {
            name: "sap-journal-api-qas",
            script: "python",
            args: "-m uvicorn app.api:app --host 0.0.0.0 --port 3019",
            interpreter: "none",
            watch: false,        // Desactivado en producción para evitar reinicios infinitos
            env: {
                NODE_ENV: "production",
            }
        }
    ]
}
