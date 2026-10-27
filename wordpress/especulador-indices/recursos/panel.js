/**
 * Gráfico de la serie de doce meses del Índice de Fricción Global.
 *
 * JAVASCRIPT PURO, SIN LIBRERÍAS. El tema JNews ya carga su propio lastre y
 * una librería de gráficos para pintar una polilínea son doscientos
 * kilobytes por una línea quebrada. Esto son cuatro.
 *
 * SE DIBUJA EN SVG, NO EN CANVAS. El SVG escala en pantallas de alta
 * densidad sin pixelarse, se imprime bien y permite poner un title accesible
 * dentro del propio dibujo. Un canvas habría exigido redibujar a mano en
 * cada cambio de tamaño.
 *
 * LAS BANDAS DE TRAMO VAN MUY TENUES a propósito. Si se pintan con fuerza,
 * el fondo compite con la serie y el lector acaba mirando los colores en vez
 * del dato.
 */
( function () {
	'use strict';

	var ALTO = 200;          // alto del área de dibujo, en unidades de SVG
	var MARGEN_DER = 34;     // sitio para las etiquetas del eje vertical

	/**
	 * Convierte la serie en una polilínea. El eje horizontal es por posición
	 * de sesión, no por fecha: así los fines de semana y los festivos no
	 * dejan huecos, que es como se dibujan las series bursátiles.
	 */
	function puntos( valores, ancho ) {
		var n = valores.length;
		if ( n < 2 ) {
			return '';
		}
		var paso = ancho / ( n - 1 );
		var trozos = [];
		for ( var i = 0; i < n; i++ ) {
			var x = ( i * paso ).toFixed( 1 );
			// El índice va de 0 a 100 y el SVG crece hacia abajo: se invierte.
			var y = ( ALTO - ( valores[ i ] / 100 ) * ALTO ).toFixed( 1 );
			trozos.push( x + ',' + y );
		}
		return trozos.join( ' ' );
	}

	/**
	 * Posiciones donde cambia el mes, para las etiquetas del eje horizontal.
	 */
	function cambiosDeMes( fechas, ancho ) {
		var paso = ancho / Math.max( 1, fechas.length - 1 );
		var marcas = [];
		var ultimo = '';
		for ( var i = 0; i < fechas.length; i++ ) {
			var mes = fechas[ i ].slice( 0, 7 );
			if ( mes !== ultimo ) {
				marcas.push( { x: i * paso, etiqueta: etiquetaMes( fechas[ i ] ) } );
				ultimo = mes;
			}
		}
		return marcas;
	}

	/**
	 * "9 mar" a partir de "2026-03-09", para la anotación del máximo.
	 */
	function diaYMes( iso ) {
		var meses = [ 'ene', 'feb', 'mar', 'abr', 'may', 'jun',
			'jul', 'ago', 'sep', 'oct', 'nov', 'dic' ];
		return parseInt( iso.slice( 8, 10 ), 10 ) + ' '
			+ ( meses[ parseInt( iso.slice( 5, 7 ), 10 ) - 1 ] || '' );
	}

	function etiquetaMes( iso ) {
		var meses = [ 'ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN',
			'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC' ];
		return meses[ parseInt( iso.slice( 5, 7 ), 10 ) - 1 ] || '';
	}

	function svg( etiqueta, atributos, hijos ) {
		var e = document.createElementNS( 'http://www.w3.org/2000/svg', etiqueta );
		for ( var k in atributos ) {
			if ( Object.prototype.hasOwnProperty.call( atributos, k ) ) {
				e.setAttribute( k, atributos[ k ] );
			}
		}
		( hijos || [] ).forEach( function ( h ) {
			e.appendChild( h );
		} );
		return e;
	}

	function dibujar( lienzo, datos ) {
		var ancho = Math.max( 280, lienzo.clientWidth - MARGEN_DER );
		var valores = datos.valores;
		var fechas = datos.fechas;

		// El viewBox se iguala al ancho real medido, así que la escala es 1:1
		// y nada se deforma. Sin preserveAspectRatio="none": estirar el
		// dibujo convertiría el círculo del máximo en una elipse y engordaría
		// el trazo de forma desigual.
		var raiz = svg( 'svg', {
			width: '100%',
			height: ALTO,
			viewBox: '0 0 ' + ( ancho + MARGEN_DER ) + ' ' + ALTO,
			role: 'img',
			'aria-label': 'Serie del Índice de Fricción Global en los últimos doce meses, de '
				+ fechas[ 0 ] + ' a ' + fechas[ fechas.length - 1 ] + '. Último valor, '
				+ valores[ valores.length - 1 ].toFixed( 1 ).replace( '.', ',' ) + '.'
		} );

		// Bandas de tramo, de arriba abajo: Extrema, Alta, Tensión, Normal, Calma.
		var techo = 100;
		( datos.tramos || [] ).slice().reverse().forEach( function ( t ) {
			raiz.appendChild( svg( 'rect', {
				x: 0,
				y: ALTO - ( techo / 100 ) * ALTO,
				width: ancho,
				height: ( t.peso / 100 ) * ALTO,
				fill: t.color,
				opacity: '0.07'
			} ) );
			techo -= t.peso;
		} );

		// Líneas de referencia en los cortes de tramo que un lector busca.
		[ 20, 50, 75, 90 ].forEach( function ( v ) {
			var y = ALTO - ( v / 100 ) * ALTO;
			raiz.appendChild( svg( 'line', {
				x1: 0, y1: y, x2: ancho, y2: y,
				stroke: 'currentColor', 'stroke-width': '1', opacity: '0.18'
			} ) );
			var t = svg( 'text', {
				x: ancho + 6, y: y + 3, 'font-size': '9',
				fill: 'currentColor', opacity: '0.55'
			} );
			t.textContent = String( v );
			raiz.appendChild( t );
		} );

		// La serie.
		raiz.appendChild( svg( 'polyline', {
			fill: 'none',
			stroke: 'currentColor',
			'stroke-width': '1.6',
			'stroke-linejoin': 'round',
			'stroke-linecap': 'round',
			points: puntos( valores, ancho ),
			'vector-effect': 'non-scaling-stroke'
		} ) );

		// El máximo del año, única anotación. Más marcas y el gráfico se
		// convierte en un artículo.
		if ( datos.maximo && datos.maximo.fecha ) {
			var i = fechas.indexOf( datos.maximo.fecha );
			if ( i >= 0 ) {
				var paso = ancho / Math.max( 1, valores.length - 1 );
				var cx = i * paso;
				var cy = ALTO - ( valores[ i ] / 100 ) * ALTO;

				raiz.appendChild( svg( 'circle', {
					cx: cx, cy: cy, r: 3.5, fill: 'none',
					stroke: '#F06A6A', 'stroke-width': '1.5'
				} ) );

				// La etiqueta se pone a la izquierda del punto si el punto
				// está en el tercio final, para que no se salga del dibujo.
				var derecha = cx > ancho * 0.7;
				var etq = svg( 'text', {
					x: derecha ? cx - 8 : cx + 8,
					y: cy + 3,
					'text-anchor': derecha ? 'end' : 'start',
					'font-size': '9.5',
					'font-weight': '600',
					fill: '#F06A6A'
				} );
				etq.textContent = datos.maximo.valor.toFixed( 1 ).replace( '.', ',' )
					+ ' · ' + diaYMes( datos.maximo.fecha );
				raiz.appendChild( etq );
			}
		}

		lienzo.innerHTML = '';
		lienzo.appendChild( raiz );

		// Etiquetas de mes, en HTML y no en SVG: así no se deforman con el
		// preserveAspectRatio="none" que estira el dibujo a lo ancho.
		var pie = document.createElement( 'div' );
		pie.className = 'esp-ifg__meses';
		pie.style.paddingRight = MARGEN_DER + 'px';
		cambiosDeMes( fechas, ancho ).forEach( function ( m ) {
			var s = document.createElement( 'span' );
			s.style.left = ( m.x / ( ancho + MARGEN_DER ) * 100 ) + '%';
			s.textContent = m.etiqueta;
			pie.appendChild( s );
		} );
		lienzo.appendChild( pie );
	}

	/**
	 * Los titulares llenan el hueco disponible y el resto se ofrece en un
	 * botón.
	 *
	 * POR QUÉ HACE FALTA MEDIR. CSS no sabe contar cuántos elementos caben.
	 * Se puede recortar con overflow, pero entonces el último titular queda
	 * cortado por la mitad, que es peor que no enseñarlo. Así que se mide
	 * elemento por elemento y se oculta el primero que se sale y los que
	 * vienen detrás.
	 *
	 * Se mide dos veces a propósito: la primera para saber si sobra algo, y
	 * la segunda ya con el botón puesto, porque el botón ocupa sitio y
	 * cambia la cuenta. Hacerlo de una sola pasada deja siempre un titular
	 * cortado debajo del botón.
	 */
	function llenarFocos( lista ) {
		var boton = lista.parentNode.querySelector( '.esp-ifg__mas' );
		var focos = Array.prototype.slice.call(
			lista.querySelectorAll( '.esp-ifg__foco' ) );
		if ( ! focos.length || ! boton ) {
			return;
		}

		// Estado abierto: se ve todo y no hay nada que medir.
		if ( lista.classList.contains( 'esp-ifg__focos--abierta' ) ) {
			return;
		}

		var marco = lista.closest( '.esp-ifg__marco' );
		if ( ! marco ) {
			return;
		}

		/*
		 * SE MIDE EL HUECO CON LOS TITULARES QUITADOS, no con ellos puestos.
		 *
		 * El atributo alto pone un min-height, y un mínimo no obliga a nada a
		 * encoger: con los titulares dentro, el bloque crece y la lista
		 * siempre "cabe" en sí misma. Preguntarle entonces cuánto mide no
		 * dice nada.
		 *
		 * Quitándolos primero, la diferencia entre lo que mide el marco y lo
		 * que ocupa su contenido es exactamente el hueco libre, venga de un
		 * min-height o de que Elementor haya estirado la columna para
		 * igualarla con la pieza de al lado. Si esa diferencia es cero, no
		 * hay nada que repartir y se enseñan todos.
		 */
		lista.hidden = false;
		focos.forEach( function ( f ) {
			f.classList.add( 'esp-ifg__foco--oculto' );
		} );
		boton.hidden = true;

		/*
		 * Y hay que apagarle el flex-grow a la lista mientras se mide. Si no,
		 * la lista se estira sola para llenar el marco y el contenido mide
		 * siempre lo mismo que el contenedor.
		 */
		var flexOriginal = lista.style.flex;
		lista.style.flex = '0 0 auto';

		/*
		 * El hueco se mide como la distancia entre el fondo del último
		 * elemento y el fondo útil del marco.
		 *
		 * NO sirve marco.clientHeight - marco.scrollHeight: scrollHeight
		 * nunca devuelve menos que clientHeight, así que esa resta da cero
		 * aunque sobre medio bloque de espacio. Es un detalle del DOM que
		 * cuesta ver porque la fórmula parece la natural.
		 */
		var ultimo = marco.lastElementChild;
		while ( ultimo && ultimo.offsetParent === null ) {
			ultimo = ultimo.previousElementSibling;
		}
		var fondoMarco = marco.getBoundingClientRect().bottom
			- parseFloat( getComputedStyle( marco ).paddingBottom || 0 );
		var hueco = ultimo
			? fondoMarco - ultimo.getBoundingClientRect().bottom
			: 0;

		/*
		 * Si el bloque no tiene ningún hueco propio —porque nadie le impone
		 * altura— se mide contra la pieza de al lado. Es lo que convierte
		 * esto en "que mida lo que mida su vecina" sin tener que escribir
		 * ningún número a mano.
		 */
		lista.style.flex = flexOriginal;

		/*
		 * Sin altura fija no hay nada que repartir: el bloque mide lo que
		 * mida su contenido y se enseñan todos los titulares. Con altura
		 * fija, en cambio, nunca se enseñan todos "porque sí": si el hueco
		 * sale negativo —la altura pedida no da ni para la cifra y el pie—
		 * se trata como cero y queda un titular con el botón detrás.
		 */
		var seccion = lista.closest( '.esp-ifg' );
		var esFijo = seccion && seccion.classList.contains( 'esp-ifg--fijo' );

		if ( ! esFijo && hueco <= 1 ) {
			focos.forEach( function ( f ) {
				f.classList.remove( 'esp-ifg__foco--oculto' );
			} );
			return;
		}
		if ( hueco < 0 ) {
			hueco = 0;
		}

		/*
		 * SI NO CABE NI UN TITULAR, se retira la lista entera en vez de
		 * forzar uno. Pedir una altura por debajo de lo que ocupan la cifra,
		 * la escala y el pie es legítimo —el bloque se queda en índice y
		 * poco más—, pero empeñarse en enseñar un titular que no cabe es lo
		 * que hacía que el contenido se saliera de la tarjeta. Si al menos
		 * cabe el botón, se deja: los titulares siguen a un clic.
		 */
		var altoBotonMin = 30;
		if ( hueco < focos[ 0 ].offsetHeight + altoBotonMin ) {
			lista.hidden = ( hueco < altoBotonMin );
			if ( ! lista.hidden ) {
				boton.hidden = false;
				boton.textContent = 'Ver ' + focos.length + ' focos abiertos';
				boton.setAttribute( 'aria-expanded', 'false' );
				engancharBoton();
			}
			return;
		}
		lista.hidden = false;

		// Se van enseñando de uno en uno mientras quepan. Hay que medir cada
		// uno ya visible, porque su alto depende de cuántas líneas ocupe su
		// titular, que no se sabe hasta dibujarlo.
		var usado = 0, corte = 0, i;
		for ( i = 0; i < focos.length; i++ ) {
			focos[ i ].classList.remove( 'esp-ifg__foco--oculto' );
			var h = focos[ i ].offsetHeight;
			if ( usado + h > hueco && i > 0 ) {
				focos[ i ].classList.add( 'esp-ifg__foco--oculto' );
				break;
			}
			usado += h;
			corte = i + 1;
		}

		if ( corte >= focos.length ) {
			return;          // caben todos: ni botón ni recorte
		}

		// Ahora el botón ocupa sitio, así que puede que haya que retirar uno
		// más. Sin esta segunda pasada, el último titular queda medio tapado.
		boton.hidden = false;
		var altoBoton = boton.offsetHeight;
		while ( corte > 1 && usado + altoBoton > hueco ) {
			corte--;
			usado -= focos[ corte ].offsetHeight;
			focos[ corte ].classList.add( 'esp-ifg__foco--oculto' );
		}
		for ( i = corte; i < focos.length; i++ ) {
			focos[ i ].classList.add( 'esp-ifg__foco--oculto' );
		}

		var ocultos = focos.length - corte;
		boton.textContent = ocultos === 1 ? 'Ver 1 foco más' : 'Ver ' + ocultos + ' focos más';
		boton.setAttribute( 'aria-expanded', 'false' );

		engancharBoton();

		function engancharBoton() {
			if ( boton.dataset.espListo ) {
				return;
			}
			boton.dataset.espListo = '1';
			boton.addEventListener( 'click', function () {
				var abierta = lista.classList.toggle( 'esp-ifg__focos--abierta' );
				boton.setAttribute( 'aria-expanded', abierta ? 'true' : 'false' );

				/*
				 * AL ABRIR HAY QUE SOLTAR LA ALTURA FIJA. Si no, la tarjeta
				 * sigue midiendo lo que se le pidió, los titulares que salen
				 * se desbordan por debajo y pisan el pie, el aviso legal y lo
				 * que haya en la página detrás. Se guarda la altura original
				 * para devolvérsela al cerrar.
				 */
				if ( seccion ) {
					if ( abierta ) {
						if ( seccion.dataset.espAlto === undefined ) {
							seccion.dataset.espAlto = seccion.style.height || '';
						}
						seccion.style.height = 'auto';
					} else {
						seccion.style.height = seccion.dataset.espAlto || '';
					}
				}

				if ( abierta ) {
					focos.forEach( function ( f ) {
						f.classList.remove( 'esp-ifg__foco--oculto' );
					} );
					boton.textContent = 'Ver menos';
				} else {
					llenarFocos( lista );
				}
			} );
		}
	}

	function arrancarFocos() {
		var listas = document.querySelectorAll( '.esp-ifg__focos--llena' );
		Array.prototype.forEach.call( listas, function ( lista ) {
			llenarFocos( lista );

			/*
			 * SE VUELVE A MEDIR CUANDO LA PÁGINA TERMINA DE CARGAR.
			 *
			 * La primera medición se hace con el DOM listo, y en ese momento
			 * las fotos de la pieza de al lado todavía no han llegado: la
			 * fila es más baja de lo que acabará siendo. Si no se repite,
			 * el bloque se queda con el reparto de aquel instante y enseña
			 * un titular donde caben cinco, con un hueco negro debajo. Era
			 * justo lo que se veía en la portada.
			 *
			 * El retardo de los 900 ms cubre además lo que llegue tarde por
			 * su cuenta: anuncios, iframes de cotizaciones, tipografías.
			 */
			function rehacer() {
				if ( ! lista.classList.contains( 'esp-ifg__focos--abierta' ) ) {
					llenarFocos( lista );
				}
			}

			window.addEventListener( 'load', rehacer );
			setTimeout( rehacer, 900 );

			var espera;
			window.addEventListener( 'resize', function () {
				clearTimeout( espera );
				espera = setTimeout( rehacer, 200 );
			} );
		} );
	}

	function arrancar() {
		arrancarFocos();
		var lienzos = document.querySelectorAll( '[data-esp-ifg]' );
		Array.prototype.forEach.call( lienzos, function ( lienzo ) {
			var datos = window.espIFG && window.espIFG[ lienzo.getAttribute( 'data-esp-ifg' ) ];
			if ( ! datos || ! datos.valores || ! datos.valores.length ) {
				return;
			}
			dibujar( lienzo, datos );

			// Redibuja al cambiar el ancho, con freno para no hacerlo en cada
			// píxel mientras se arrastra el borde de la ventana.
			var espera;
			window.addEventListener( 'resize', function () {
				clearTimeout( espera );
				espera = setTimeout( function () {
					dibujar( lienzo, datos );
				}, 200 );
			} );
		} );
	}

	if ( document.readyState === 'loading' ) {
		document.addEventListener( 'DOMContentLoaded', arrancar );
	} else {
		arrancar();
	}
}() );
