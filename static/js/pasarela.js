// 🔥 Cargar total del carrito
async function cargarTotal() {
    const res = await fetch('/api/cart');
    const data = await res.json();

    document.getElementById("totalCompra").innerText =
        "COP " + data.total_price.toLocaleString('es-CO');
}

cargarTotal();

// 🔥 Cambiar método de pago
document.getElementById("metodo").addEventListener("change", cargarDatosPago);
cargarDatosPago();

function cargarDatosPago() {
    let metodo = document.getElementById("metodo").value;

    fetch(`/api/datos-pago?metodo=${metodo}`)
        .then(res => res.json())
        .then(data => {

            let d = data.datos;
            let html = "";

            if (metodo === "nequi") {
                html = `📱 ${d.numero}<br>👤 ${d.titular}`;
            }

            if (metodo === "banco") {
                html = `🏦 ${d.banco}<br>Cuenta: ${d.numero}<br>${d.titular}`;
            }

            if (metodo === "efecty") {
                html = `Convenio: ${d.convenio}<br>${d.titular}`;
            }

            document.getElementById("infoPago").innerHTML = html;
        });
}

// 🔥 Crear pedido REAL
function crearPedido() {
    const nombre = document.getElementById("nombre").value;
    const email = document.getElementById("email").value;
    const metodo = document.getElementById("metodo").value;
    const telefono = document.getElementById("telefono").value;

    if (!nombre || !email) {
        alert("Completa tus datos");
        return;
    }

    fetch("/api/crear-pedido", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            metodo: metodo,
            nombre: nombre,
            email: email,
            telefono: telefono
        })
    })
    .then(res => res.json())
    .then(data => {
        document.getElementById("resultado").innerHTML = `
            <b>Pedido creado ✅</b><br>
            Referencia: ${data.referencia}<br>
            Total: COP ${data.precio.toLocaleString()}
        `;
    });
}