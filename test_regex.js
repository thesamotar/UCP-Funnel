const text = `Here's a detailed comparison of your shortlisted earbuds:

| Feature | boAt Nirvana Ion (CROM-106) | OnePlus Nord Buds 3r |
|---|---|---|
| **Price** | ₹1,799 | ₹1,849 |
| **Battery** | 120 Hours | 54 Hours |
`;

let html = text;
if (html.includes('|')) {
    html = html.replace(/((?:^[ \t]*\|.*\|\r?\n?)+)/gm, function(match) {
      let rows = match.trim().split(/\r?\n/);
      if (rows.length < 2) return match;
      let tableHtml = '<table class="md-table">';
      rows.forEach((row, index) => {
        if (row.match(/^[ \t]*\|(?:-+|:?-+:?|\||\s)+\|[ \t]*$/)) return;
        let cols = row.split('|').slice(1, -1);
        tableHtml += '<tr>';
        cols.forEach(col => {
          tableHtml += (index === 0) ? `<th>${col.trim()}</th>` : `<td>${col.trim()}</td>`;
        });
        tableHtml += '</tr>';
      });
      tableHtml += '</table>';
      return tableHtml;
    });
}
console.log(html);
