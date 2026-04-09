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
        html = `
          <b>📱 Pagar con Nequi</b><br><br>
          Número: ${d.numero}<br>
          Titular: ${d.titular}
        `;
      }

      if (metodoSeleccionado === "banco") {
        html = `
          <b>🏦 Transferencia Bancaria</b><br><br>
          Banco: ${d.banco}<br>
          Cuenta: ${d.numero}<br>
          Tipo: ${d.tipo}<br>
          Titular: ${d.titular}
        `;
      }

      if (metodoSeleccionado === "efecty") {
        html = `
          <b>💵 Pago por Efecty</b><br><br>
          Convenio: ${d.convenio}<br>
          Titular: ${d.titular}
        `;
      }

      document.getElementById("infoPago").innerHTML = html;
    });
}

// CREAR PEDIDO
document.getElementById("btnPagar").addEventListener("click", () => {

  const telefono = document.getElementById("telefono").value;
  const nombre   = document.getElementById("nombre").value;
  const email    = document.getElementById("email").value;

  fetch("/api/crear-pedido", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      metodo: metodoSeleccionado,
      nombre: nombre,
      email: email,
      telefono: telefono
    })
  })
  .then(res => {
    if (res.status === 401) {
        window.location.href = "/login";
        return;
    }
    return res.json();
})
.then(data => {
    if (!data) return;
    const resultado = document.getElementById("resultado");
    resultado.innerHTML = `
      ✅ ¡Pedido confirmado!<br>
      🧾 Ref: ${data.referencia}<br>
      💰 Total: $${data.precio.toLocaleString()}<br>
      ⚠️ Realiza el pago y envía el comprobante.
    `;
    resultado.classList.add("show");
    document.getElementById("btnPagar").disabled = true;

    setTimeout(() => {
      window.location.href = "/inicioU";
    }, 3000);
  })
  .catch(err => {
    console.error("Error:", err);
  });

}); // <-- cierre del addEventListener

// CARGA INICIAL
cargarDatosPago();