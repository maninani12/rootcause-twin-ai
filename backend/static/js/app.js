"use strict";
const demoData = document.getElementById("demo-data");
if (demoData) {
  const demos = JSON.parse(demoData.dataset.values);
  const form = document.getElementById("incident-form");
  document.querySelectorAll("[data-demo]").forEach(button => {
    button.addEventListener("click", () => {
      const incident = demos[button.dataset.demo];
      Object.entries(incident).forEach(([name, value]) => {
        if (form.elements.namedItem(name)) form.elements.namedItem(name).value = value;
      });
      form.elements.namedItem("demo").value = button.dataset.demo;
      document.getElementById("demo-status").textContent = `${button.dataset.demo} loaded — synthetic context, real Hindsight recall.`;
      form.elements.namedItem("machine").focus();
    });
  });
}
document.querySelectorAll("form[data-loading]").forEach(form => {
  form.addEventListener("submit", event => {
    if (form.dataset.submitting === "true") { event.preventDefault(); return; }
    form.dataset.submitting = "true";
    form.querySelectorAll("button").forEach(button => { button.disabled = true; });
    const status = form.querySelector(".loading");
    if (status) status.textContent = form.dataset.loading;
  });
});
window.addEventListener("pageshow", event => {
  if (event.persisted) window.location.reload();
});
