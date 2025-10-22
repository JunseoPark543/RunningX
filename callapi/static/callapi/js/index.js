let marker = null;
let map = null;

function initTmap() {
  // 기본 지도 생성 (초기 위치는 서울시청)
  map = new Tmapv2.Map("map_div", {
    center: new Tmapv2.LatLng(37.5665, 126.9780),
    width: "100%",
    height: "400px",
    zoom: 16
  });

  // 현재 위치 요청
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      function (position) {
        const lat = position.coords.latitude;
        const lon = position.coords.longitude;

        // 지도 중심 변경
        const userLocation = new Tmapv2.LatLng(lat, lon);
        map.setCenter(userLocation);

        // 현재 위치에 마커 찍기 (선택사항)
        new Tmapv2.Marker({
          position: userLocation,
          map: map,
          title: "현재 위치"
        });
      },
      function (error) {
        console.warn("위치 정보를 가져올 수 없습니다.", error);
      }
    );
  } else {
    alert("이 브라우저에서는 위치 정보를 지원하지 않습니다.");
  }

  // 지도 클릭 리스너
  map.addListener("click", function (evt) {
    const lat = evt.latLng.lat();
    const lon = evt.latLng.lng();

    if (marker) marker.setMap(null);
    marker = new Tmapv2.Marker({
      position: new Tmapv2.LatLng(lat, lon),
      map: map
    });

    fetch(`https://apis.openapi.sk.com/tmap/geo/reversegeocoding?version=1&format=json&coordType=WGS84GEO&addressType=A10&lon=${lon}&lat=${lat}`, {
      method: "GET",
      headers: { "appKey": "OF93Av1S5v2pHZvLIqzpUaq7OYEpaKFKa9yKt0NF" }
    })
    .then(res => res.json())
    .then(data => {
      const address = data.addressInfo.fullAddress;
      document.getElementById("latInput").value = lat;
      document.getElementById("lonInput").value = lon;
      document.getElementById("addressInput").value = address;
    });
  });
}

window.onload = initTmap;



