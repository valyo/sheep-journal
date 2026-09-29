// Show only the fields that apply to the chosen event type.
(function () {
  const form = document.getElementById("entry-form");
  const select = document.getElementById("event_type");
  if (!form || !select) return;
  const ppn = document.getElementById("ppn");

  function update() {
    const option = select.selectedOptions[0];
    const data = option ? option.dataset : {};
    const show = {
      movement: data.movement === "1",
      transport: data.transport === "1",
      death: select.value === "death",
    };
    form.querySelectorAll("[data-show]").forEach((el) => {
      el.hidden = !show[el.dataset.show];
    });
    if (select.value === "birth" && ppn && !ppn.value) {
      ppn.value = form.dataset.ownPpn;
    }
  }

  select.addEventListener("change", update);
  update();
})();
