"""Flask 项目入口"""
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def root():
    return jsonify({"message": "Hello BlueDeer"})

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
