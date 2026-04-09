let metodoSeleccionado = "nequi";

// CAMBIAR MÉTODO
document.querySelectorAll(".metodo").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".metodo").forEach(b => b.classList.remove("activo"));
    btn.classList.add("activo");
    metodoSeleccionado = btn.dataset.metodo;
    cargarDatosPago();
  });
});

// CARGAR DATOS DEL BACKEND
function cargarDatosPago() {
  fetch(`/api/datos-pago?metodo=${metodoSeleccionado}`)
    .then(res => res.json())
    .then(data => {
      let d = data.datos;
      let html = "";

      if (metodoSeleccionado === "nequi") {
        html = `<b>📱 Pagar con Nequi</b><br><br>Número: ${d.numero}<br>Titular: ${d.titular}`;
      }
      if (metodoSeleccionado === "banco") {
        html = `<b>🏦 Transferencia Bancaria</b><br><br>Banco: ${d.banco}<br>Cuenta: ${d.numero}<br>Tipo: ${d.tipo}<br>Titular: ${d.titular}`;
      }
      if (metodoSeleccionado === "efecty") {
        html = `<b>💵 Pago por Efecty</b><br><br>Convenio: ${d.convenio}<br>Titular: ${d.titular}`;
      }

      document.getElementById("infoPago").innerHTML = html;
    })
    .catch(err => console.error("Error cargando datos de pago:", err));
}

// CREAR PEDIDO
document.getElementById("btnPagar").addEventListener("click", () => {

  const telefono = document.getElementById("telefono").value;
  const nombre   = document.getElementById("nombre").value;
  const email    = document.getElementById("email").value;
  const btn      = document.getElementById("btnPagar");

  btn.disabled = true;
  btn.textContent = "Procesando...";

  fetch("/api/crear-pedido", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ metodo: metodoSeleccionado, nombre, email, telefono })
  })
  .then(res => {
    if (!res.ok) return res.json().then(e => { throw new Error(e.error || res.status); });
    return res.json();
  })
  .then(data => {
    const resultado = document.getElementById("resultado");
    resultado.innerHTML = `
      ✅ ¡Pedido confirmado!<br>
      🧾 Ref: ${data.referencia}<br>
      💰 Total: $${data.total.toLocaleString()}<br>
      ⚠️ Realiza el pago y envía el comprobante.<br><br>
      Redirigiendo...
    `;
    resultado.classList.add("show");

    setTimeout(() => {
      window.location.href = "/inicioU";
    }, 3000);
  })
  .catch(err => {
    console.error("Error:", err);
    const btn = document.getElementById("btnPagar");
    btn.disabled = false;
    btn.textContent = "Confirmar pedido";

    const resultado = document.getElementById("resultado");
    resultado.innerHTML = `❌ Error: ${err.message}`;
    resultado.classList.add("show");
    resultado.style.background = "#fdecea";
    resultado.style.color = "#c0392b";
  });
});

// CARGA INICIAL
cargarDatosPago();