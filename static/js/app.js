document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("invoiceForm");
  if (!form) return;

  const money = n => new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR"
  }).format(Number(n || 0));

  const field = name => form.querySelector(`[name="${name}"]`);
  const preview = document.getElementById("billPreview");

  const designFields = [
      "background_color",
      "label_color",
      "font_color",
      "accent_color",
      "border_color",
      "font_family",
      "font_size",
      "layout_style"
  ];

  // Five available invoice templates.
  const themes = {
      "Classic": [
          "#fffdf8", "#5b4636", "#493d34", "#9b7653", "#e3d8ca"
      ],
      "Modern": [
          "#f7fbff", "#173f70", "#24364b", "#1685c5", "#d8e6f2"
      ],
      "Creative": [
          "#fff8fb", "#713b67", "#48354a", "#cf579f", "#ead4e4"
      ],
      "Premium": [
          "#fbf9ff", "#43336b", "#3e3850", "#8064c8", "#e0d9ef"
      ],
      "Business Pro": [
          "#f5f7fa", "#1d3557", "#26364a", "#0077a8", "#d5dce5"
      ]
  };

  function updatePreview() {
      const total = Number(field("total_amount")?.value || 0);
      const paid = Number(field("paid_amount")?.value || 0);
      const balance = total - paid;

      const balanceInput = document.getElementById("balance_amount_display");
      const summary = document.getElementById("balance_summary");

      if (balanceInput) balanceInput.value = balance.toFixed(2);
      if (summary) summary.textContent = money(balance);

      const put = (id, value) => {
          const el = document.getElementById(id);
          if (el) el.textContent = value || "—";
      };

      put("previewCustomer", field("customer_name")?.value);
      put("previewPurpose", field("purpose")?.value);
      put("previewTotal", money(total));
      put("previewBalance", money(balance));

      const chosen = form.querySelector(
          'input[name="template_name"]:checked'
      );

      const templateName = chosen?.value || "Modern";
      put("previewTemplate", templateName);

      if (preview) {
          const colorFields = {
              "--invoice-bg": "background_color",
              "--invoice-label": "label_color",
              "--invoice-font": "font_color",
              "--invoice-accent": "accent_color",
              "--invoice-border": "border_color"
          };

          Object.entries(colorFields).forEach(([variable, name]) => {
              const input = field(name);
              if (input) preview.style.setProperty(variable, input.value);
          });

          preview.style.fontFamily = field("font_family")?.value || "Helvetica";
          preview.style.fontSize = `${field("font_size")?.value || 9}px`;
          preview.dataset.layout = field("layout_style")?.value || "Standard";
          preview.dataset.template = templateName;
      }
  }

  function applyTheme(name) {
      const palette = themes[name];
      if (!palette) return;

      [
          "background_color",
          "label_color",
          "font_color",
          "accent_color",
          "border_color"
      ].forEach((id, index) => {
          const input = document.getElementById(id);
          if (input) input.value = palette[index];
      });

      updatePreview();
  }

  // Apply the selected template's theme.
  document.querySelectorAll('input[name="template_name"]').forEach(radio => {
      radio.addEventListener("change", () => applyTheme(radio.value));
  });

  form.addEventListener("input", updatePreview);
  form.addEventListener("change", updatePreview);

  // Save and load custom designs in this browser.
  const designSnapshot = () => Object.fromEntries(
      designFields.map(name => [name, field(name)?.value || ""])
  );

  const storageKey = "istInvoiceSavedDesignsV2";

  function readDesigns() {
      try {
          return JSON.parse(localStorage.getItem(storageKey) || "{}");
      } catch {
          return {};
      }
  }

  function refreshDesignList() {
      const select = document.getElementById("savedDesigns");
      if (!select) return;

      const current = select.value;
      select.innerHTML = '<option value="">Load saved design...</option>';

      Object.keys(readDesigns()).sort().forEach(name => {
          const option = document.createElement("option");
          option.value = name;
          option.textContent = name;
          select.appendChild(option);
      });

      select.value = current;
  }

  document.getElementById("saveDesign")?.addEventListener("click", () => {
      const name = prompt("Name this invoice design:");
      if (!name?.trim()) return;

      const designs = readDesigns();
      designs[name.trim()] = {
          template_name: form.querySelector(
              'input[name="template_name"]:checked'
          )?.value || "Modern",
          ...designSnapshot()
      };

      localStorage.setItem(storageKey, JSON.stringify(designs));
      refreshDesignList();

      const select = document.getElementById("savedDesigns");
      if (select) select.value = name.trim();

      alert("Design saved in this browser.");
  });

  document.getElementById("loadDesign")?.addEventListener("click", () => {
      const name = document.getElementById("savedDesigns")?.value;
      const design = readDesigns()[name];

      if (!design) {
          alert("Select a saved design first.");
          return;
      }

      if (design.template_name) {
          const radio = form.querySelector(
              `input[name="template_name"][value="${CSS.escape(design.template_name)}"]`
          );
          if (radio) radio.checked = true;
      }

      Object.entries(design).forEach(([key, value]) => {
          if (key !== "template_name" && field(key)) {
              field(key).value = value;
          }
      });

      updatePreview();
  });

  document.getElementById("resetDesign")?.addEventListener("click", () => {
      const modernRadio = form.querySelector(
          'input[name="template_name"][value="Modern"]'
      );

      if (modernRadio) modernRadio.checked = true;

      applyTheme("Modern");

      if (field("font_family")) field("font_family").value = "Helvetica";
      if (field("font_size")) field("font_size").value = "9";
      if (field("layout_style")) field("layout_style").value = "Standard";

      updatePreview();
  });

  refreshDesignList();

  // Company seal preview.
  const sealInput = document.getElementById("seal");
  const sealPreview = document.getElementById("sealPreview");

  sealInput?.addEventListener("change", () => {
      if (!sealPreview) return;

      sealPreview.innerHTML = "";
      const file = sealInput.files?.[0];

      if (!file) return;

      if (!/^image\/(png|jpeg)$/.test(file.type)) {
          alert("Please choose a PNG or JPG company seal.");
          sealInput.value = "";
          return;
      }

      const img = document.createElement("img");
      img.src = URL.createObjectURL(file);
      img.alt = "Company seal preview";
      sealPreview.appendChild(img);
  });

  // Signature previews and upload limit.
  const signatureInput = document.getElementById("signatures");
  const signaturePreview = document.getElementById("signaturePreview");

  signatureInput?.addEventListener("change", () => {
      if (!signaturePreview) return;

      signaturePreview.innerHTML = "";

      if (signatureInput.files.length > 4) {
          signatureInput.value = "";
          alert("You can upload a maximum of four signatures.");
          return;
      }

      [...signatureInput.files].forEach(file => {
          if (!/^image\/(png|jpeg)$/.test(file.type)) {
              alert("Signature images must be PNG or JPG.");
              signatureInput.value = "";
              signaturePreview.innerHTML = "";
              return;
          }

          const img = document.createElement("img");
          img.alt = "Signature preview";
          img.src = URL.createObjectURL(file);
          signaturePreview.appendChild(img);
      });
  });

  // Form validation.
  form.addEventListener("submit", event => {
      const total = Number(field("total_amount")?.value || 0);
      const paid = Number(field("paid_amount")?.value || 0);

      if (paid > total) {
          event.preventDefault();
          alert("Paid amount cannot exceed total amount.");
          return;
      }

      const balanceDue = field("balance_due_date")?.value;
      const billing = field("billing_date")?.value;

      if (total > paid && !balanceDue) {
          event.preventDefault();
          alert("Please select the balance due date.");
          return;
      }

      if (balanceDue && billing && balanceDue < billing) {
          event.preventDefault();
          alert("Balance due date cannot be earlier than billing date.");
          return;
      }

      const selectedSignatures = document.querySelectorAll(
          'input[name="selected_signatures"]:checked'
      ).length;

      if (selectedSignatures > 4) {
          event.preventDefault();
          alert("Choose a maximum of four signatures.");
      }
  });

  document.getElementById("resetButton")?.addEventListener("click", () => {
      setTimeout(() => {
          if (signaturePreview) signaturePreview.innerHTML = "";
          if (sealPreview) sealPreview.innerHTML = "";

          const modernRadio = form.querySelector(
              'input[name="template_name"][value="Modern"]'
          );
          if (modernRadio) modernRadio.checked = true;

          applyTheme("Modern");
          updatePreview();
      }, 0);
  });

  // Set Modern as the initial template and load its colors.
  const initialTemplate = form.querySelector(
      'input[name="template_name"]:checked'
  );

  if (initialTemplate) {
      applyTheme(initialTemplate.value);
  } else {
      applyTheme("Modern");
  }

  updatePreview();
});