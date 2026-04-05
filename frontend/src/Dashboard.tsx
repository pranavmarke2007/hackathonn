import { useEffect, useState } from "react";

export default function Dashboard() {
  const [emails, setEmails] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("http://127.0.0.1:5000/emails")
      .then(res => res.json())
      .then(data => {
        console.log("Emails:", data);
        setEmails(data);
        setLoading(false);
      })
      .catch(err => {
        console.error("Error:", err);
        setLoading(false);
      });
  }, []);

  return (
    <div style={{ padding: "20px" }}>
      <h1>📥 Inbox Dashboard</h1>

      {loading ? (
        <p>Loading emails...</p>
      ) : emails.length === 0 ? (
        <p>No emails found</p>
      ) : (
        emails.map((mail, i) => (
          <div
            key={i}
            style={{
              border: "1px solid #ccc",
              margin: "10px",
              padding: "10px",
              borderRadius: "8px"
            }}
          >
            <p><b>From:</b> {mail.from}</p>
            <p><b>Status:</b> {mail.status}</p>
          </div>
        ))
      )}
    </div>
  );
}