export async function GET() {
  const response = await fetch("https://www.strava.com/oauth/token", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      client_id: "262271",
      client_secret: "d5c36f980ba41ff448f5f27deb700dda19170251",
      code: "415fa20de095697f66ab9c3fe3484087da66f5a6",
      grant_type: "authorization_code",
    }),
  });

  const data = await response.json();

  return Response.json(data);
}