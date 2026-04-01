import React from "react";

const Paywall = () => {
  return (
    <div style={{
      minHeight: "80vh",
      display: "flex",
      justifyContent: "center",
      alignItems: "center",
      background: "#0a0a0a",
      color: "#fff"
    }}>
      <div style={{
        border: "1px solid gold",
        padding: "40px",
        borderRadius: "12px",
        textAlign: "center",
        maxWidth: "400px",
        boxShadow: "0 0 20px rgba(0,255,100,0.2)"
      }}>
        <h2 style={{ color: "gold" }}>Upgrade Required</h2>

        <p style={{ marginTop: "20px" }}>
          This is a premium AI tool.<br />
          Subscribe to unlock full access.
        </p>

        <button
          style={{
            marginTop: "30px",
            padding: "12px 20px",
            background: "gold",
            color: "#000",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
            fontWeight: "bold"
          }}
        >
          💳 Upgrade Now
        </button>
      </div>
    </div>
  );
};

export default Paywall;