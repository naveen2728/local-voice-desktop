const $ = (id) => document.getElementById(id);

const defaultBody = `Dear $first_name,

I hope you are doing well. My name is $sender_name, and I am writing to express my interest in exploring suitable opportunities at $company.

I am a fresher with a strong interest in learning, growing, and applying my skills in a practical, real-world environment. I am highly motivated, quick to learn, and comfortable adapting to new tools, technologies, and responsibilities based on the needs of the role.

I would be grateful for an opportunity to contribute and grow under the guidance of experienced professionals. I am open to internships, trainee roles, or any suitable entry-level position where I can add value and learn continuously.

I have attached my resume for your consideration. Thank you for your time and support.

Warm regards,
$sender_name

If this is not relevant, no worries. Just let me know and I will not follow up.`;

function payload() {
  return {
    csvPath: $("csvPath").value.trim(),
    attachmentPath: $("attachmentPath").value.trim(),
    fromEmail: $("fromEmail").value.trim(),
    senderName: $("senderName").value.trim(),
    senderCompany: $("senderCompany").value.trim(),
    smtpHost: $("smtpHost").value.trim(),
    smtpPort: Number($("smtpPort").value || 587),
    smtpUsername: $("smtpUsername").value.trim(),
    smtpPassword: $("smtpPassword").value,
    skip: Number($("skip").value || 0),
    batchSize: Number($("batchSize").value || 10),
    delaySeconds: Number($("delaySeconds").value || 90),
    subject: "Quick question about $company",
    body: defaultBody,
  };
}

async function postJson(url, data) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || "Request failed");
  return result;
}

function setStatus(text, tone = "ready") {
  $("serverStatus").textContent = text;
  $("serverStatus").style.background = tone === "bad" ? "#fff1f0" : tone === "busy" ? "#fff7e6" : "#eaf7ef";
  $("serverStatus").style.borderColor = tone === "bad" ? "#f4b6ad" : tone === "busy" ? "#ffd591" : "#b9e4c7";
  $("serverStatus").style.color = tone === "bad" ? "#b42318" : tone === "busy" ? "#ad6800" : "#176b3a";
}

async function preview() {
  try {
    setStatus("Previewing", "busy");
    const result = await postJson("/api/preview", payload());
    $("eligibleMetric").textContent = `Eligible: ${result.stats.eligible}`;
    $("batchMetric").textContent = `Batch: ${result.batchSize}`;
    $("missingMetric").textContent = `Missing basis: ${result.stats.missing_lawful_basis}`;
    $("previewTo").textContent = `To: ${result.first.email}`;
    $("previewSubject").textContent = `Subject: ${result.first.subject}`;
    $("previewBody").textContent = result.first.body;
    setStatus("Ready");
  } catch (error) {
    setStatus(error.message, "bad");
  }
}

async function markRange() {
  try {
    setStatus("Marking", "busy");
    const result = await postJson("/api/mark-range", {
      csvPath: $("csvPath").value.trim(),
      startRow: Number($("startRow").value || 1),
      endRow: Number($("endRow").value || 1),
    });
    setStatus(result.message);
    await preview();
  } catch (error) {
    setStatus(error.message, "bad");
  }
}

async function sendBatch() {
  try {
    setStatus("Starting", "busy");
    const result = await postJson("/api/send", payload());
    setStatus(result.message, "busy");
  } catch (error) {
    setStatus(error.message, "bad");
  }
}

async function stopBatch() {
  try {
    const result = await postJson("/api/stop", {});
    setStatus(result.message, "busy");
  } catch (error) {
    setStatus(error.message, "bad");
  }
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    $("sentCount").textContent = status.sent;
    $("failedCount").textContent = status.failed;
    $("totalCount").textContent = status.total;
    if (status.running) setStatus(status.current ? `Sending ${status.current}` : "Sending", "busy");
    const rows = status.events
      .slice()
      .reverse()
      .map(
        (event) =>
          `<tr><td>${event.time}</td><td>${event.email}</td><td>${event.outcome}</td><td>${event.detail || ""}</td></tr>`,
      )
      .join("");
    $("events").innerHTML = rows;
  } catch {
    setStatus("Server offline", "bad");
  }
}

$("preview").addEventListener("click", preview);
$("markRange").addEventListener("click", markRange);
$("send").addEventListener("click", sendBatch);
$("stop").addEventListener("click", stopBatch);

setInterval(refreshStatus, 2000);
refreshStatus();
