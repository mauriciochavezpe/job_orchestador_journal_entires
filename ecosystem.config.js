// ecosystem.config.js
module.exports = {
    apps: [
        {
            name: "sap-journal-api",
            script: "python",
            args: "-m uvicorn app.api:app --host 0.0.0.0 --port 3018",
            interpreter: "none", // Usamos el comando directo de python
            watch: false,        // Desactivado en producción para evitar reinicios infinitos
            env: {
                NODE_ENV: "production",
            }
        }
    ]
}
